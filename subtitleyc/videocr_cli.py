from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from .process import popen_hidden_subprocess

ProgressCallback = Callable[[float, str], None]
ProcessCallback = Callable[[subprocess.Popen[str]], None]


class VideOCRCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class VideOCRCliSettings:
    crop_x: int
    crop_y: int
    crop_width: int
    crop_height: int
    language: str = "ch"
    frames_to_skip: int = 0
    conf_threshold: int = 65
    sim_threshold: int = 72
    max_merge_gap: float = 0.0
    use_fullframe: bool = False
    use_gpu: bool = False
    use_angle_cls: bool = False
    use_server_model: bool = True
    brightness_threshold: int | None = None
    ssim_threshold: int = 88
    subtitle_position: str = "center"
    normalize_to_simplified_chinese: bool = True
    post_processing: bool = False
    min_subtitle_duration: float = 0.04
    ocr_image_max_width: int = 1280
    use_dual_zone: bool = False
    start_seconds: float = 0.0
    end_seconds: float | None = None


_CLI_CANDIDATES = (
    r"C:\Program Files\VideOCR\videocr-cli-CPU-v1.4.0\videocr-cli.exe",
    r"C:\Program Files\VideOCR\videocr-cli-GPU-v1.4.0\videocr-cli.exe",
    r"C:\Program Files\VideOCR\videocr-cli.exe",
    r"C:\Program Files (x86)\VideOCR\videocr-cli-CPU-v1.4.0\videocr-cli.exe",
)

_PROGRESS_PATTERNS = (
    (re.compile(r"Mapping frame (\d+) of (\d+)", re.IGNORECASE), 0.02, 0.12),
    (re.compile(r"Step 1: Processing image (\d+) of (\d+)", re.IGNORECASE), 0.12, 0.40),
    (re.compile(r"Step 2: Performing OCR on image (\d+) of (\d+)", re.IGNORECASE), 0.45, 0.93),
)


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_videocr_cli(prefer_gpu: bool = False) -> str | None:
    env_path = os.environ.get("VIDEOCR_CLI")
    candidates: list[Path] = []
    if env_path and (not prefer_gpu or "cpu" not in env_path.casefold()):
        candidates.append(Path(env_path))
    tools_dir = _runtime_root() / "tools"
    build_names = (
        ["videocr-cli-GPU-v1.4.0"]
        if prefer_gpu
        else ["videocr-cli-CPU-v1.4.0", "videocr-cli-GPU-v1.4.0"]
    )
    for prefix in (tools_dir, tools_dir / "VideOCR"):
        candidates.extend(prefix / name / "videocr-cli.exe" for name in build_names)
        candidates.append(prefix / "videocr-cli.exe")

    installed_candidates = [Path(candidate) for candidate in _CLI_CANDIDATES]
    if prefer_gpu:
        installed_candidates = [
            path for path in installed_candidates if "cpu" not in str(path).casefold()
        ]
    installed_candidates.sort(
        key=lambda path: (
            0 if "gpu" in str(path).casefold() else 1,
            str(path).casefold(),
        )
    )
    candidates.extend(installed_candidates)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    roots = [tools_dir, Path(r"C:\Program Files\VideOCR"), Path(r"C:\Program Files (x86)\VideOCR")]
    for root in roots:
        if root.is_dir():
            matches = list(root.glob("**/videocr-cli.exe"))
            if prefer_gpu:
                matches = [
                    path
                    for path in matches
                    if "gpu" in str(path).casefold() or path.parent == root
                ]
            matches.sort(
                key=lambda path: (
                    0 if "gpu" in str(path).casefold() else 1,
                    str(path).casefold(),
                )
            )
            if matches:
                return str(matches[0])
    return None

_LANGUAGE_ALIASES = {
    "eng": "en",
    "chi_sim": "ch",
    "eng+chi_sim": "ch",
    "chi_tra": "chinese_cht",
    "eng+chi_tra": "chinese_cht",
}

_SUPPORTED_PADDLEOCR_LANGUAGES = frozenset(
    {
        "ar",
        "ch",
        "chinese_cht",
        "de",
        "en",
        "es",
        "fa",
        "fr",
        "hi",
        "id",
        "it",
        "japan",
        "kk",
        "korean",
        "mn",
        "mr",
        "ms",
        "ne",
        "pt",
        "ru",
        "ta",
        "te",
        "th",
        "tl",
        "tr",
        "ug",
        "uk",
        "ur",
        "vi",
    }
)


def map_language(language: str) -> str:
    normalized = language.strip().casefold()
    mapped = _LANGUAGE_ALIASES.get(normalized, normalized)
    if mapped not in _SUPPORTED_PADDLEOCR_LANGUAGES:
        raise ValueError(f"Unsupported VideOCR language: {language}")
    return mapped


def bool_arg(value: bool) -> str:
    return "true" if value else "false"


def seconds_to_cli_time(seconds: float) -> str:
    safe = max(0, int(round(seconds)))
    hours, remainder = divmod(safe, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes}:{secs:02}"


def count_srt_cues(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d+\s*$", text))


def _runtime_env(runtime_dir: Path) -> dict[str, str]:
    temp_dir = runtime_dir / "temp"
    local_appdata = runtime_dir / "localappdata"
    appdata = runtime_dir / "appdata"
    for directory in (temp_dir, local_appdata, appdata):
        directory.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "LOCALAPPDATA": str(local_appdata),
            "APPDATA": str(appdata),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def _build_args(video_path: Path, output_path: Path, settings: VideOCRCliSettings) -> list[str]:
    args = [
        "--video_path",
        str(video_path),
        "--output",
        str(output_path),
        "--lang",
        settings.language,
        "--time_start",
        seconds_to_cli_time(settings.start_seconds),
        "--conf_threshold",
        str(settings.conf_threshold),
        "--sim_threshold",
        str(settings.sim_threshold),
        "--max_merge_gap",
        str(settings.max_merge_gap),
        "--use_fullframe",
        bool_arg(settings.use_fullframe),
        "--use_gpu",
        bool_arg(settings.use_gpu),
        "--use_angle_cls",
        bool_arg(settings.use_angle_cls),
        "--use_server_model",
        bool_arg(settings.use_server_model),
        "--ssim_threshold",
        str(settings.ssim_threshold),
        "--subtitle_position",
        settings.subtitle_position,
        "--frames_to_skip",
        str(settings.frames_to_skip),
        "--normalize_to_simplified_chinese",
        bool_arg(settings.normalize_to_simplified_chinese),
        "--post_processing",
        bool_arg(settings.post_processing),
        "--min_subtitle_duration",
        str(settings.min_subtitle_duration),
        "--ocr_image_max_width",
        str(settings.ocr_image_max_width),
        "--crop_x",
        str(settings.crop_x),
        "--crop_y",
        str(settings.crop_y),
        "--crop_width",
        str(settings.crop_width),
        "--crop_height",
        str(settings.crop_height),
        "--allow_system_sleep",
        "false",
    ]
    if settings.end_seconds is not None:
        args.extend(["--time_end", seconds_to_cli_time(settings.end_seconds)])
    if settings.brightness_threshold is not None:
        args.extend(["--brightness_threshold", str(settings.brightness_threshold)])
    return args


def _progress_from_message(message: str) -> tuple[float, str] | None:
    if "Starting PaddleOCR" in message:
        return 0.42, "Starting PaddleOCR"
    if "Generating subtitles" in message:
        return 0.96, "Generating subtitles"
    for pattern, start, end in _PROGRESS_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        current = int(match.group(1))
        total = max(1, int(match.group(2)))
        ratio = start + (min(current, total) / total) * (end - start)
        return ratio, message
    return None


def _tail(values: list[str], limit: int = 12) -> str:
    return "\n".join(values[-limit:])


def _read_error_log(runtime_dir: Path) -> str:
    log_path = runtime_dir / "localappdata" / "VideOCR" / "paddleocr_error.log"
    if not log_path.is_file():
        return ""
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
    except OSError:
        return ""


def run_videocr_cli(
    video_path: Path,
    output_path: Path,
    settings: VideOCRCliSettings,
    runtime_dir: Path,
    progress: ProgressCallback | None = None,
    cli_path: str | None = None,
    cancel_event: Event | None = None,
    process_callback: ProcessCallback | None = None,
) -> str:
    cli = cli_path or find_videocr_cli(prefer_gpu=settings.use_gpu)
    if not cli:
        raise RuntimeError(
            "VideOCR CLI was not found. Install VideOCR or set VIDEOCR_CLI to videocr-cli.exe."
        )

    runtime_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    args = [cli, *_build_args(video_path, output_path, settings)]
    env = _runtime_env(runtime_dir)
    if progress:
        progress(0.01, "Starting real VideOCR CLI")

    process = popen_hidden_subprocess(
        args,
        cwd=str(Path(cli).parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    messages: list[str] = []
    segment = ""
    if process_callback:
        process_callback(process)
    def _cancelled() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def _stop_process() -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    assert process.stdout is not None
    while True:
        if _cancelled():
            _stop_process()
            raise VideOCRCancelled("VideOCR job was cancelled.")
        chunk = process.stdout.read(1)
        if chunk == "" and process.poll() is not None:
            break
        if not chunk:
            continue
        if chunk in "\r\n":
            clean = re.sub(r"\s+", " ", segment).strip()
            if clean:
                messages.append(clean)
                parsed = _progress_from_message(clean)
                if parsed and progress:
                    progress(*parsed)
            segment = ""
        else:
            segment += chunk

    clean = re.sub(r"\s+", " ", segment).strip()
    if clean:
        messages.append(clean)
        parsed = _progress_from_message(clean)
        if parsed and progress:
            progress(*parsed)

    return_code = process.wait()
    if _cancelled():
        raise VideOCRCancelled("VideOCR job was cancelled.")
    if return_code != 0 or not output_path.is_file():
        details = _tail(messages)
        log_text = _read_error_log(runtime_dir)
        if log_text:
            details = f"{details}\n{log_text}" if details else log_text
        raise RuntimeError(
            f"VideOCR CLI failed with exit code {return_code}." + (f"\n{details}" if details else "")
        )

    if progress:
        progress(0.99, "Reading VideOCR SRT")
    return output_path.read_text(encoding="utf-8-sig", errors="replace")

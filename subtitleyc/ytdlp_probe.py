from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from .process import install_hidden_yt_dlp_subprocesses, run_hidden_subprocess
from .security import public_network_only, validate_public_http_url


_FORMAT_FIELDS = (
    "format_id",
    "vcodec",
    "acodec",
    "ext",
    "fps",
    "dynamic_range",
    "format_note",
    "resolution",
    "width",
    "height",
    "tbr",
    "filesize",
    "filesize_approx",
)


class ProbeLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def debug(self, message: str) -> None:
        if not str(message).startswith("[debug]"):
            self._append(message)

    def warning(self, message: str) -> None:
        self._append(f"WARNING: {message}")

    def error(self, message: str) -> None:
        self._append(f"ERROR: {message}")

    def _append(self, message: str) -> None:
        clean = str(message).strip()
        if clean:
            self.lines.append(clean)
            self.lines = self.lines[-12:]

    def tail(self) -> str:
        return "\n".join(self.lines[-8:])


def _is_bilibili_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").casefold().strip(".")
    except ValueError:
        return False
    return host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com")


def _headers(url: str) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    }
    if _is_bilibili_url(url):
        headers.update(
            {
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )
    return headers


def _safe_youtube_dl(yt_dlp_module: Any, options: dict[str, Any]) -> Any:
    class SubtitleYCProbeYoutubeDL(yt_dlp_module.YoutubeDL):
        def _forceprint(self, key: str, info_dict: dict[str, Any] | None) -> None:
            forceprint = self.params.get("forceprint") or {}
            print_to_file = self.params.get("print_to_file") or {}
            if not (forceprint.get(key) or print_to_file.get(key)):
                return None
            return super()._forceprint(key, info_dict)

    safe = dict(options)
    safe.update(
        {
            "ignoreconfig": True,
            "encoding": "utf-8",
            "forceprint": {},
            "print_to_file": {},
            "listformats": False,
            "listformats_table": False,
            "listsubtitles": False,
            "list_thumbnails": False,
        }
    )
    return SubtitleYCProbeYoutubeDL(safe)


def _subtitle_map(value: Any) -> dict[str, list[dict[str, str]]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[dict[str, str]]] = {}
    for language, entries in value.items():
        safe_entries: list[dict[str, str]] = []
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    extension = str(entry.get("ext") or "").strip()
                    safe_entries.append({"ext": extension})
        result[str(language)] = safe_entries
    return result


def probe_in_process(action: str, url: str) -> dict[str, Any]:
    import yt_dlp

    if action not in {"formats", "subtitles"}:
        raise ValueError(f"Unknown yt-dlp probe action: {action}")

    url = validate_public_http_url(url)
    install_hidden_yt_dlp_subprocesses()
    logger = ProbeLogger()
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": False,
        "logger": logger,
        "noplaylist": True,
        "proxy": "",
        "restrictfilenames": True,
        "http_headers": _headers(url),
    }
    try:
        with public_network_only(), _safe_youtube_dl(yt_dlp, options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        details = logger.tail()
        message = str(exc)
        if details and details not in message:
            message = f"{message}\n{details}"
        raise RuntimeError(message) from exc

    if not isinstance(info, dict):
        return {"title": "", "formats": [], "subtitles": {}, "automatic_captions": {}}

    if action == "formats":
        formats = [
            {field: item.get(field) for field in _FORMAT_FIELDS}
            for item in (info.get("formats") or [])
            if isinstance(item, dict)
        ]
        return {"title": str(info.get("title") or ""), "formats": formats}

    return {
        "title": str(info.get("title") or ""),
        "subtitles": _subtitle_map(info.get("subtitles")),
        "automatic_captions": _subtitle_map(info.get("automatic_captions")),
    }


def _worker_command(action: str, url: str, result_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--yt-dlp-probe-worker", action, url, str(result_path)]
    return [sys.executable, "-m", "subtitleyc.ytdlp_probe", "--worker", action, url, str(result_path)]


def probe_in_subprocess(action: str, url: str, timeout_seconds: int = 120) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="subtitleyc-ytdlp-probe-"))
    result_path = temp_dir / "result.json"
    try:
        command = _worker_command(action, url, result_path)
        try:
            completed = run_hidden_subprocess(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
                env=dict(os.environ),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("The yt-dlp format check timed out") from exc

        payload: dict[str, Any] = {}
        if result_path.is_file():
            try:
                loaded = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except (OSError, json.JSONDecodeError):
                payload = {}

        if payload.get("ok") and isinstance(payload.get("result"), dict):
            return payload["result"]

        error = str(payload.get("error") or "").strip()
        if not error:
            error = (completed.stderr or completed.stdout or "").strip()
        if not error:
            error = f"yt-dlp probe helper exited with code {completed.returncode}"
        raise RuntimeError(error)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def worker_main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "--worker":
        args = args[1:]
    if len(args) != 3:
        return 2

    action, url, raw_result_path = args
    result_path = Path(raw_result_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = {"ok": True, "result": probe_in_process(action, url)}
        exit_code = 0
    except BaseException as exc:
        payload = {"ok": False, "error": str(exc), "type": type(exc).__name__}
        exit_code = 1

    try:
        result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return 3
    return exit_code


if __name__ == "__main__":
    raise SystemExit(worker_main())

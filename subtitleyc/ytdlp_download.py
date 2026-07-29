from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .process import install_hidden_yt_dlp_subprocesses, popen_hidden_subprocess
from .security import public_network_only, validate_public_http_url


class YtDlpDownloadCancelled(RuntimeError):
    pass


class _DownloadLogger:
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
            self.lines = self.lines[-16:]

    def tail(self) -> str:
        return "\n".join(self.lines[-10:])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _safe_youtube_dl(yt_dlp_module: Any, options: dict[str, Any]) -> Any:
    class SubtitleYCDownloadYoutubeDL(yt_dlp_module.YoutubeDL):
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
    return SubtitleYCDownloadYoutubeDL(safe)


def _downloaded_path(info: Any) -> str:
    if not isinstance(info, dict):
        return ""
    for key in ("filepath", "_filename"):
        value = info.get(key)
        if isinstance(value, str) and value:
            return value
    for item in info.get("requested_downloads") or []:
        if not isinstance(item, dict):
            continue
        for key in ("filepath", "_filename"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


class _ProgressWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.last_write = 0.0
        self.lock = threading.Lock()

    def __call__(self, event: dict[str, Any]) -> None:
        with self.lock:
            status = str(event.get("status") or "")
            now = time.monotonic()
            if status == "downloading" and now - self.last_write < 0.08:
                return
            self.last_write = now
            payload = {
                "status": status,
                "downloaded_bytes": event.get("downloaded_bytes") or 0,
                "total_bytes": event.get("total_bytes") or event.get("total_bytes_estimate") or 0,
                "speed": event.get("speed") or 0,
            }
            try:
                _write_json(self.path, payload)
            except OSError:
                pass


def worker_main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "--worker":
        args = args[1:]
    if len(args) != 3:
        return 2

    raw_request_path, raw_result_path, raw_progress_path = args
    request_path = Path(raw_request_path)
    result_path = Path(raw_result_path)
    progress_path = Path(raw_progress_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    logger = _DownloadLogger()
    fault_log_handle: Any = None

    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise RuntimeError("Invalid yt-dlp download request")
        url = str(request.get("url") or "").strip()
        options = request.get("options")
        if not url or not isinstance(options, dict):
            raise RuntimeError("The yt-dlp download request is incomplete")
        url = validate_public_http_url(url)

        raw_fault_log_path = str(request.get("fault_log_path") or "").strip()
        if raw_fault_log_path:
            import faulthandler

            fault_log_path = Path(raw_fault_log_path)
            fault_log_path.parent.mkdir(parents=True, exist_ok=True)
            fault_log_handle = fault_log_path.open("a", encoding="utf-8", buffering=1)
            faulthandler.enable(file=fault_log_handle, all_threads=True)

        import yt_dlp

        install_hidden_yt_dlp_subprocesses()
        options = dict(options)
        options["logger"] = logger
        options["progress_hooks"] = [_ProgressWriter(progress_path)]
        with public_network_only(), _safe_youtube_dl(yt_dlp, options) as ydl:
            info = ydl.extract_info(url, download=True)
        payload = {
            "ok": True,
            "result": {
                "title": str(info.get("title") or "") if isinstance(info, dict) else "",
                "filepath": _downloaded_path(info),
                "messages": logger.lines,
            },
        }
        exit_code = 0
    except BaseException as exc:
        message = str(exc).strip() or type(exc).__name__
        details = logger.tail()
        if details and details not in message:
            message = f"{message}\n{details}"
        payload = {"ok": False, "error": message, "type": type(exc).__name__}
        exit_code = 1

    try:
        _write_json(result_path, payload)
    except OSError:
        exit_code = 3
    if fault_log_handle is not None:
        try:
            import faulthandler

            faulthandler.disable()
            fault_log_handle.close()
        except Exception:
            pass
    return exit_code


def _worker_command(request_path: Path, result_path: Path, progress_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--yt-dlp-download-worker", str(request_path), str(result_path), str(progress_path)]
    return [
        sys.executable,
        "-m",
        "subtitleyc.ytdlp_download",
        "--worker",
        str(request_path),
        str(result_path),
        str(progress_path),
    ]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def download_in_subprocess(
    url: str,
    options: dict[str, Any],
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: Any = None,
    process_callback: Callable[[subprocess.Popen[Any]], None] | None = None,
    fault_log_path: Path | None = None,
) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="subtitleyc-ytdlp-download-"))
    request_path = temp_dir / "request.json"
    result_path = temp_dir / "result.json"
    progress_path = temp_dir / "progress.json"
    process: subprocess.Popen[Any] | None = None
    try:
        _write_json(
            request_path,
            {
                "url": url,
                "options": options,
                "fault_log_path": str(fault_log_path) if fault_log_path else "",
            },
        )
        process = popen_hidden_subprocess(
            _worker_command(request_path, result_path, progress_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=dict(os.environ),
        )
        if process_callback:
            process_callback(process)

        last_progress_stamp = -1
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise YtDlpDownloadCancelled("Download cancelled")

            try:
                progress_stamp = progress_path.stat().st_mtime_ns
            except OSError:
                progress_stamp = -1
            if progress and progress_stamp != -1 and progress_stamp != last_progress_stamp:
                last_progress_stamp = progress_stamp
                payload = _read_json(progress_path)
                if payload:
                    progress(payload)
            time.sleep(0.08)

        if cancel_event is not None and cancel_event.is_set():
            raise YtDlpDownloadCancelled("Download cancelled")
        if progress:
            payload = _read_json(progress_path)
            if payload:
                progress(payload)

        payload = _read_json(result_path)
        result = payload.get("result")
        if payload.get("ok") and isinstance(result, dict):
            return result

        error = str(payload.get("error") or "").strip()
        if not error:
            code = process.returncode
            error = f"The yt-dlp download worker stopped unexpectedly (exit code {code})."
            if code not in (0, 1, 2, 3):
                error += " The download engine crashed, but SubtitleYC remained open."
        raise RuntimeError(error)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(worker_main())

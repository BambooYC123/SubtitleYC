from __future__ import annotations

import atexit
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

_STANDARD_STREAM: TextIO | None = None
APP_TITLE = "SubtitleYC"


def _ensure_standard_streams() -> None:
    global _STANDARD_STREAM
    if sys.stdout is not None and sys.stderr is not None:
        return
    _STANDARD_STREAM = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _STANDARD_STREAM
    if sys.stderr is None:
        sys.stderr = _STANDARD_STREAM


_ensure_standard_streams()

import uvicorn  # noqa: E402


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _desktop_data_dir() -> Path:
    configured = os.environ.get("SUBTITLEYC_DATA_DIR")
    if configured:
        return Path(configured)
    if getattr(sys, "frozen", False):
        for env_name in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env_name)
            if base:
                return Path(base) / APP_TITLE / "workspace"
    return _runtime_root() / "workspace"


def _write_desktop_crash(title: str, details: str) -> None:
    try:
        crash_dir = _desktop_data_dir() / "logs" / "crashes"
        crash_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = crash_dir / f"{stamp}-{title}.log"
        path.write_text(details, encoding="utf-8")
        _log(f"Crash log written: {path}")
    except Exception:
        pass

def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").casefold() in {"1", "true", "yes", "on"}


_INSTANCE_MUTEX_HANDLE: int | None = None


def _claim_single_instance() -> bool:
    if _truthy_env("SUBTITLEYC_ALLOW_MULTIPLE") or sys.platform != "win32":
        return True
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.wintypes.LPVOID, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        handle = kernel32.CreateMutexW(None, False, "Local\\SubtitleYCDesktop")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            _log("Another SubtitleYC instance is already starting or running")
            return False
        global _INSTANCE_MUTEX_HANDLE
        _INSTANCE_MUTEX_HANDLE = int(handle)
        atexit.register(lambda: kernel32.CloseHandle(_INSTANCE_MUTEX_HANDLE))
        return True
    except Exception as error:  # noqa: BLE001 - launch should continue if the guard fails.
        _log(f"Single-instance guard unavailable: {error}")
        return True

def _log(message: str) -> None:
    if not _truthy_env("SUBTITLEYC_DESKTOP_LOG"):
        return
    try:
        log_path = _runtime_root() / "subtitleyc-desktop.log"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass

class StartupIndicator:
    def __init__(self) -> None:
        self._queue = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()

    def start(self) -> "StartupIndicator":
        if _truthy_env("SUBTITLEYC_DISABLE_STARTUP_INDICATOR"):
            return self
        try:
            import queue

            commands = queue.Queue()
        except Exception as exc:  # noqa: BLE001 - startup indicator is best-effort only.
            _log(f"Startup indicator unavailable: {exc}")
            return self

        self._queue = commands

        def run_window() -> None:
            try:
                import tkinter as tk
                from tkinter import ttk

                root = tk.Tk()
                root.title(APP_TITLE)
                root.resizable(False, False)
                root.configure(bg="#0d131a")
                root.protocol("WM_DELETE_WINDOW", lambda: None)
                try:
                    root.attributes("-topmost", True)
                except tk.TclError:
                    pass

                width, height = 360, 142
                root.update_idletasks()
                x = max(0, (root.winfo_screenwidth() - width) // 2)
                y = max(0, (root.winfo_screenheight() - height) // 2)
                root.geometry(f"{width}x{height}+{x}+{y}")

                frame = tk.Frame(root, bg="#0d131a", padx=18, pady=16)
                frame.pack(fill="both", expand=True)
                title_row = tk.Frame(frame, bg="#0d131a")
                title_row.pack(fill="x")
                logo = tk.Label(title_row, text="SYC", bg="#020617", fg="#ffffff", width=5, height=2, font=("Segoe UI", 9, "bold"))
                logo.pack(side="left", padx=(0, 12))
                text_box = tk.Frame(title_row, bg="#0d131a")
                text_box.pack(side="left", fill="x", expand=True)
                tk.Label(text_box, text="SubtitleYC is opening", bg="#0d131a", fg="#e7edf5", anchor="w", font=("Segoe UI", 12, "bold")).pack(fill="x")
                tk.Label(text_box, text="Loading tools and preview engine", bg="#0d131a", fg="#98a6b7", anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(3, 0))
                progress = ttk.Progressbar(frame, mode="indeterminate")
                progress.pack(fill="x", pady=(18, 0))
                progress.start(12)

                def poll() -> None:
                    try:
                        command = commands.get_nowait()
                    except queue.Empty:
                        root.after(100, poll)
                        return
                    if command == "close":
                        root.destroy()
                        return
                    root.after(100, poll)

                root.after(100, poll)
                root.mainloop()
            except Exception as exc:  # noqa: BLE001 - never block app startup for the indicator.
                _log(f"Startup indicator failed: {exc}")
            finally:
                self._closed.set()

        self._thread = threading.Thread(target=run_window, name="SubtitleYCStartupIndicator", daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        commands = self._queue
        if commands is None:
            return
        try:
            commands.put_nowait("close")
        except Exception:  # noqa: BLE001 - best-effort shutdown.
            pass
        self._closed.wait(timeout=2)

def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _pick_port(preferred: int | None = None) -> int:
    if preferred is not None and _port_is_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _open_browser(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


class DesktopApi:
    def __init__(self, base_url: str) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        self.app_token = os.environ.get("SUBTITLEYC_API_TOKEN", "")

    def choose_video_file(self, current_path: str = "") -> dict[str, object]:
        import webview

        window = webview.windows[0] if webview.windows else None
        if window is None:
            return {"ok": False, "message": "Video picker is unavailable."}

        start_dir = Path(os.path.expandvars(current_path or "")).expanduser() if current_path else Path.home()
        if not start_dir.is_dir():
            videos_dir = Path.home() / "Videos"
            start_dir = videos_dir if videos_dir.is_dir() else Path.home()

        selection = window.create_file_dialog(
            webview.OPEN_DIALOG,
            directory=str(start_dir),
            allow_multiple=False,
            file_types=("Video files (*.mp4;*.mkv;*.webm;*.mov;*.m4v;*.avi)", "All files (*.*)"),
        )
        if not selection:
            return {"ok": False, "cancelled": True}

        selected_path = selection[0] if isinstance(selection, (list, tuple)) else selection
        return {"ok": True, "path": str(Path(str(selected_path)))}
    def choose_download_dir(self, current_path: str = "") -> dict[str, object]:
        import webview

        window = webview.windows[0] if webview.windows else None
        if window is None:
            return {"ok": False, "message": "Folder picker is unavailable."}

        start_dir = Path(os.path.expandvars(current_path or "")).expanduser() if current_path else Path.home()
        if not start_dir.is_dir():
            downloads_dir = Path.home() / "Downloads"
            start_dir = downloads_dir if downloads_dir.is_dir() else Path.home()

        selection = window.create_file_dialog(webview.FOLDER_DIALOG, directory=str(start_dir))
        if not selection:
            return {"ok": False, "cancelled": True}

        selected_path = selection[0] if isinstance(selection, (list, tuple)) else selection
        return {"ok": True, "path": str(Path(str(selected_path)))}

    def choose_subtitle_save_path(self, suggested_name: str = "subtitles.srt") -> dict[str, object]:
        import webview

        window = webview.windows[0] if webview.windows else None
        if window is None:
            return {"ok": False, "message": "Save dialog is unavailable."}

        safe_name = Path(suggested_name or "subtitles.srt").name
        if Path(safe_name).suffix.casefold() != ".srt":
            safe_name = f"{Path(safe_name).stem or 'subtitles'}.srt"

        selection = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=safe_name,
            file_types=("SubRip subtitles (*.srt)", "All files (*.*)"),
        )
        if not selection:
            return {"ok": False, "cancelled": True}

        selected_path = selection[0] if isinstance(selection, (list, tuple)) else selection
        target = Path(str(selected_path))
        if target.suffix.casefold() != ".srt":
            target = target.with_suffix(".srt")
        return {"ok": True, "path": str(target)}

    def save_subtitle(self, subtitle_url: str, suggested_name: str = "subtitles.srt") -> dict[str, object]:
        if not subtitle_url:
            return {"ok": False, "message": "No subtitle file is available yet."}

        import webview

        window = webview.windows[0] if webview.windows else None
        if window is None:
            return {"ok": False, "message": "Save dialog is unavailable."}

        file_types_by_suffix = {
            ".srt": ("SubRip subtitles (*.srt)", "srt"),
            ".txt": ("Plain text subtitles (*.txt)", "txt"),
            ".ass": ("Advanced SubStation Alpha (*.ass)", "ass"),
        }
        safe_name = Path(suggested_name or "subtitles.srt").name
        suffix = Path(safe_name).suffix.casefold()
        if suffix not in file_types_by_suffix:
            suffix = ".srt"
            safe_name = f"{Path(safe_name).stem or 'subtitles'}{suffix}"

        file_label, extension = file_types_by_suffix[suffix]
        selection = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=safe_name,
            file_types=(file_label, "All files (*.*)"),
        )
        if not selection:
            return {"ok": False, "cancelled": True}

        selected_path = selection[0] if isinstance(selection, (list, tuple)) else selection
        target = Path(str(selected_path))
        if target.suffix.casefold() != suffix:
            target = target.with_suffix(suffix)

        url = urllib.parse.urljoin(f"{self.base_url}/", subtitle_url.lstrip("/"))
        parsed_url = urllib.parse.urlsplit(url)
        parsed_base = urllib.parse.urlsplit(self.base_url)
        if (parsed_url.scheme.casefold(), parsed_url.netloc.casefold()) != (
            parsed_base.scheme.casefold(),
            parsed_base.netloc.casefold(),
        ):
            return {"ok": False, "message": "Subtitle download must stay inside SubtitleYC."}
        download_request = urllib.request.Request(url, headers={"X-SubtitleYC-Token": self.app_token})
        with urllib.request.urlopen(download_request, timeout=30) as response:
            target.write_bytes(response.read())
        return {"ok": True, "path": str(target), "format": extension}

    def save_srt(self, srt_url: str, suggested_name: str = "subtitles.srt") -> dict[str, object]:
        return self.save_subtitle(srt_url, suggested_name)

    def open_file_location(self, target_path: str = "") -> dict[str, object]:
        if not target_path:
            return {"ok": False, "message": "No folder path is available."}
        target = Path(os.path.expandvars(target_path)).expanduser()
        if not target.exists():
            return {"ok": False, "message": f"Location does not exist: {target}"}
        folder = target if target.is_dir() else target.parent
        if sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            webbrowser.open(folder.as_uri())
        return {"ok": True, "path": str(folder)}

    def open_subtitle_editor(self, session_id: str = "", time_seconds: float = 0.0) -> dict[str, object]:
        clean_session_id = str(session_id or "")
        query_values: dict[str, str] = {}
        if clean_session_id:
            query_values.update({"session": clean_session_id, "time": f"{float(time_seconds or 0.0):.6f}"})
        if self.app_token:
            query_values["app_token"] = self.app_token
        query = urllib.parse.urlencode(query_values)
        url = f"{self.base_url}/editor" + (f"?{query}" if query else "")
        webbrowser.open(url, new=2)
        return {"ok": True, "url": url}

def _wait_for_server(url: str, app_token: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(
                f"{url}/api/system",
                headers={"X-SubtitleYC-Token": app_token},
            )
            with urllib.request.urlopen(request, timeout=1):
                _log("Server health check passed")
                return
        except Exception as exc:  # noqa: BLE001 - startup probes can fail in several harmless ways.
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"SubtitleYC did not start in time: {last_error}")


def _build_server(port: int) -> uvicorn.Server:
    _log(f"Building uvicorn server on port {port}")
    config = uvicorn.Config(
        "subtitleyc.main:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        access_log=False,
        log_level=os.environ.get("SUBTITLEYC_LOG_LEVEL", "warning"),
    )
    return uvicorn.Server(config)


def _start_server_thread(port: int, url: str, app_token: str) -> tuple[uvicorn.Server, threading.Thread]:
    server = _build_server(port)
    thread = threading.Thread(target=server.run, name="SubtitleYCServer", daemon=True)
    thread.start()
    _wait_for_server(url, app_token)
    return server, thread


def _open_desktop_window(url: str, on_ready: Callable[[], None] | None = None) -> None:
    _log("Opening desktop window")
    import webview

    webview.create_window(
        APP_TITLE,
        url,
        width=1280,
        height=840,
        min_size=(980, 680),
        confirm_close=False,
        js_api=DesktopApi(url),
    )
    if on_ready:
        on_ready()
    webview.start(debug=_truthy_env("SUBTITLEYC_WEBVIEW_DEBUG"))


def _open_qt_desktop_window(url: str, on_ready: Callable[[], None] | None = None) -> bool:
    if _truthy_env("SUBTITLEYC_DISABLE_QT_PREVIEW"):
        return False
    try:
        from subtitleyc.qt_desktop import run_qt_desktop
    except ImportError as exc:
        _log(f"Qt preview host unavailable; falling back to pywebview: {exc}")
        return False
    run_qt_desktop(url, on_ready=on_ready)
    return True


def _run_private_desktop(
    base_url: str,
    launch_url: str,
    port: int,
    app_token: str,
    on_ready: Callable[[], None] | None = None,
) -> None:
    server, thread = _start_server_thread(port, base_url, app_token)
    try:
        if not _open_qt_desktop_window(launch_url, on_ready=on_ready):
            _open_desktop_window(launch_url, on_ready=on_ready)
    finally:
        if on_ready:
            on_ready()
        _log("Stopping private backend")
        server.should_exit = True
        thread.join(timeout=5)


def _run_browser_mode(
    base_url: str,
    launch_url: str,
    port: int,
    app_token: str,
    opener: Callable[[str], None] | None = None,
) -> None:
    if opener:
        threading.Thread(target=opener, args=(launch_url,), daemon=True).start()
    server = _build_server(port)
    _log("Running backend in foreground")
    server.run()


def run() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--yt-dlp-download-worker":
        from subtitleyc.ytdlp_download import worker_main as ytdlp_download_worker_main

        raise SystemExit(ytdlp_download_worker_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--yt-dlp-probe-worker":
        from subtitleyc.ytdlp_probe import worker_main as ytdlp_probe_worker_main

        raise SystemExit(ytdlp_probe_worker_main(sys.argv[2:]))

    if not _claim_single_instance():
        return

    try:
        configured = os.environ.get("SUBTITLEYC_PORT")
        port = _pick_port(int(configured)) if configured else _pick_port()
        base_url = f"http://127.0.0.1:{port}"
        app_token = secrets.token_urlsafe(32)
        os.environ["SUBTITLEYC_API_TOKEN"] = app_token
        launch_url = f"{base_url}/?{urllib.parse.urlencode({'app_token': app_token})}"
        _log(
            "Launcher starting "
            f"port={port} no_browser={_truthy_env('SUBTITLEYC_NO_BROWSER')} "
            f"use_browser={_truthy_env('SUBTITLEYC_USE_BROWSER')} frozen={getattr(sys, 'frozen', False)}"
        )

        if _truthy_env("SUBTITLEYC_NO_BROWSER"):
            _run_browser_mode(base_url, launch_url, port, app_token)
            return

        if _truthy_env("SUBTITLEYC_USE_BROWSER"):
            _run_browser_mode(base_url, launch_url, port, app_token, _open_browser)
            return

        startup_indicator = StartupIndicator().start()
        try:
            _run_private_desktop(base_url, launch_url, port, app_token, on_ready=startup_indicator.close)
        except ImportError:
            _log("pywebview unavailable; falling back to browser")
            _run_browser_mode(base_url, launch_url, port, app_token, _open_browser)
    except Exception:  # noqa: BLE001 - keep windowed failures diagnosable.
        details = traceback.format_exc()
        _write_desktop_crash("launcher-crash", details)
        _log(details)
        raise

if __name__ == "__main__":
    run()

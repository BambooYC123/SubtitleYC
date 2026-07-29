from __future__ import annotations

import subprocess
import sys
from types import ModuleType
from typing import Any


def _add_safe_text_decoding(kwargs: dict[str, Any]) -> dict[str, Any]:
    text_mode = bool(
        kwargs.get("text")
        or kwargs.get("universal_newlines")
        or kwargs.get("encoding") is not None
        or kwargs.get("errors") is not None
    )
    if not text_mode:
        return kwargs
    kwargs["text"] = True
    if kwargs.get("encoding") is None:
        kwargs["encoding"] = "utf-8"
    if kwargs.get("errors") is None:
        kwargs["errors"] = "replace"
    return kwargs


def hidden_subprocess_kwargs(**kwargs: Any) -> dict[str, Any]:
    if sys.platform != "win32":
        return kwargs

    _add_safe_text_decoding(kwargs)
    kwargs["creationflags"] = int(kwargs.get("creationflags") or 0) | subprocess.CREATE_NO_WINDOW
    if kwargs.get("startupinfo") is None:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


def run_hidden_subprocess(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(*args, **hidden_subprocess_kwargs(**kwargs))


def popen_hidden_subprocess(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
    return subprocess.Popen(*args, **hidden_subprocess_kwargs(**kwargs))


def install_hidden_yt_dlp_subprocesses() -> None:
    if sys.platform != "win32":
        return

    try:
        import yt_dlp.utils as yt_dlp_utils
    except ImportError:
        return

    original_popen = yt_dlp_utils.Popen
    if getattr(original_popen, "_subtitleyc_hidden_windows", False):
        return

    class HiddenYtDlpPopen(original_popen):  # type: ignore[misc, valid-type]
        _subtitleyc_hidden_windows = True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _add_safe_text_decoding(kwargs)
            kwargs["creationflags"] = int(kwargs.get("creationflags") or 0) | subprocess.CREATE_NO_WINDOW

            super().__init__(*args, **kwargs)

    yt_dlp_utils.Popen = HiddenYtDlpPopen

    for module in list(sys.modules.values()):
        if not _is_yt_dlp_module(module):
            continue
        if getattr(module, "Popen", None) is original_popen:
            setattr(module, "Popen", HiddenYtDlpPopen)


def _is_yt_dlp_module(module: object) -> bool:
    if not isinstance(module, ModuleType):
        return False
    name = getattr(module, "__name__", "")
    return name == "yt_dlp" or name.startswith("yt_dlp.")

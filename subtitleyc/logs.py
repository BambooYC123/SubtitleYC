from __future__ import annotations

import faulthandler
import json
import logging
import os
import re
import sys
import threading
import traceback
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any


MAX_MEMORY_ENTRIES = 1000
LOG_FORMAT = "%(asctime)s %(levelname)s %(category)s %(job_id)s %(message)s"
LOGGER_NAME = "subtitleyc"


_entries: deque[dict[str, Any]] = deque(maxlen=MAX_MEMORY_ENTRIES)
_lock = Lock()
_crash_log_dir: Path | None = None
_fault_log_handle: Any | None = None
_hooks_installed = False
_original_excepthook = sys.excepthook
_original_threading_excepthook = getattr(threading, "excepthook", None)
_original_unraisablehook = getattr(sys, "unraisablehook", None)

_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_WINDOWS_USER_PATTERN = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s\"']+")
_UNIX_USER_PATTERN = re.compile(r"(?i)(?<![A-Za-z0-9_])/(?:home|Users)/[^/\s\"']+")
_QUOTED_PATH_PATTERN = re.compile(
    r"(?P<quote>[\"'])(?:[A-Z]:\\|/)[^\"'\r\n]+(?P=quote)",
    re.IGNORECASE,
)
_KEYED_PATH_PATTERN = re.compile(
    r"(?i)(\b(?:data_dir|output_dir|source|cli|path|folder|file)=)(?:[A-Z]:\\|/).*?(?=\s+[A-Za-z_]+=|$)"
)
_PATH_TAIL_PATTERN = re.compile(
    r"(?im)(\b(?:copying|to|from Previous Projects|stored subtitle)\s+)(?:[A-Z]:\\|/)[^\r\n]+$"
)
_TOKEN_PATTERN = re.compile(
    r"(?i)\b(app_token|x-subtitleyc-token|authorization|cookie|password|secret|token)\s*([:=])\s*([^\s,;]+)"
)
_JSON_SECRET_PATTERN = re.compile(
    r"(?i)([\"'](?:app_token|x-subtitleyc-token|authorization|cookie|password|secret|token)[\"']\s*:\s*[\"'])(.*?)([\"'])"
)
_JSON_PATH_PATTERN = re.compile(
    r"(?i)([\"'](?:data_dir|output_dir|source|cli|path|folder|file)[\"']\s*:\s*[\"'])(?:[A-Z]:\\|/).*?([\"'])"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def _redact_url_match(match: re.Match[str]) -> str:
    candidate = match.group(0)
    trailing = ""
    while candidate and candidate[-1] in ".,;)]}":
        trailing = candidate[-1] + trailing
        candidate = candidate[:-1]
    try:
        parsed = urllib.parse.urlsplit(candidate)
        hostname = parsed.hostname or ""
        if not hostname:
            return "<REDACTED_URL>" + trailing
        host = f"[{hostname}]" if ":" in hostname else hostname
        port = parsed.port
        netloc = f"{host}:{port}" if port else host
        has_sensitive_part = bool(parsed.username or parsed.password or parsed.query or parsed.fragment)
        has_path = parsed.path not in {"", "/"}
        suffix = "/<REDACTED>" if has_sensitive_part or has_path else ""
        return f"{parsed.scheme.casefold()}://{netloc}{suffix}{trailing}"
    except ValueError:
        return "<REDACTED_URL>" + trailing


def redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
    text = _URL_PATTERN.sub(_redact_url_match, text)

    roots = [
        (os.environ.get("USERPROFILE"), "<USER_HOME>"),
        (os.environ.get("HOME"), "<USER_HOME>"),
        (os.environ.get("LOCALAPPDATA"), "<LOCAL_APP_DATA>"),
        (os.environ.get("APPDATA"), "<APP_DATA>"),
        (os.environ.get("TEMP"), "<TEMP>"),
        (os.environ.get("TMP"), "<TEMP>"),
    ]
    for root, replacement in sorted(roots, key=lambda item: len(item[0] or ""), reverse=True):
        if root and len(root) >= 4:
            text = re.sub(re.escape(root), replacement, text, flags=re.IGNORECASE)

    app_token = os.environ.get("SUBTITLEYC_API_TOKEN", "")
    if len(app_token) >= 8:
        text = text.replace(app_token, "<REDACTED_TOKEN>")
    text = _WINDOWS_USER_PATTERN.sub("<USER_HOME>", text)
    text = _UNIX_USER_PATTERN.sub("<USER_HOME>", text)
    text = _QUOTED_PATH_PATTERN.sub(
        lambda match: f"{match.group('quote')}<LOCAL_PATH>{match.group('quote')}",
        text,
    )
    text = _KEYED_PATH_PATTERN.sub(lambda match: f"{match.group(1)}<LOCAL_PATH>", text)
    text = _PATH_TAIL_PATTERN.sub(lambda match: f"{match.group(1)}<LOCAL_PATH>", text)
    text = _JSON_PATH_PATTERN.sub(lambda match: f"{match.group(1)}<LOCAL_PATH>{match.group(2)}", text)
    text = _JSON_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}<REDACTED>{match.group(3)}", text)
    text = _TOKEN_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}<REDACTED>", text)
    return _BEARER_PATTERN.sub("Bearer <REDACTED>", text)


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.getMessage())
        record.args = ()
        return True


class _LogBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
        entry = {
            "timestamp": timestamp,
            "level": record.levelname,
            "category": str(getattr(record, "category", "app")),
            "job_id": str(getattr(record, "job_id", "")),
            "message": record.getMessage(),
        }
        with _lock:
            _entries.append(entry)


def _entry_matches(entry: dict[str, Any], category: str | None, level: str | None) -> bool:
    if category and category != "all" and entry.get("category") != category:
        return False
    if level and level != "all" and entry.get("level") != level:
        return False
    return True


def configure_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    old_handlers = list(logger.handlers)
    logger.handlers.clear()
    logger.filters.clear()
    logger.addFilter(_RedactingFilter())
    for handler in old_handlers:
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = RotatingFileHandler(
        log_dir / "subtitleyc.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    buffer_handler = _LogBufferHandler()
    buffer_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(buffer_handler)
    return logger


def _safe_crash_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return (clean or "crash")[:80]


def _crash_dir() -> Path:
    global _crash_log_dir
    if _crash_log_dir is None:
        _crash_log_dir = Path.cwd() / "crashes"
    _crash_log_dir.mkdir(parents=True, exist_ok=True)
    return _crash_log_dir


def record_crash(
    title: str,
    exc: BaseException | None = None,
    *,
    traceback_text: str | None = None,
    extra: dict[str, Any] | None = None,
    category: str = "crash",
    job_id: str = "",
) -> Path | None:
    try:
        now = datetime.now(timezone.utc)
        crash_dir = _crash_dir()
        path = crash_dir / f"{now.strftime('%Y%m%d-%H%M%S')}-{_safe_crash_name(title)}-{threading.get_ident()}.log"
        lines = [
            f"title: {title}",
            f"timestamp_utc: {now.isoformat()}",
            f"thread: {threading.current_thread().name} ({threading.get_ident()})",
        ]
        if job_id:
            lines.append(f"job_id: {job_id}")
        if extra:
            try:
                lines.append("extra: " + json.dumps(extra, ensure_ascii=False, indent=2, default=str))
            except TypeError:
                lines.append(f"extra: {extra!r}")
        if traceback_text:
            lines.extend(["", "traceback:", traceback_text.rstrip()])
        elif exc is not None:
            lines.extend(["", "traceback:", "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()])
        elif not extra:
            lines.append("No exception details were supplied.")
        path.write_text(redact_sensitive_text("\n".join(lines)) + "\n", encoding="utf-8")
        log_event(f"Crash log written: {path}", category=category, level=logging.ERROR, job_id=job_id)
        return path
    except Exception:  # noqa: BLE001 - crash logging must never cause another crash.
        return None


def install_crash_logging(log_dir: Path) -> None:
    global _crash_log_dir, _fault_log_handle, _hooks_installed
    _crash_log_dir = log_dir / "crashes"
    _crash_log_dir.mkdir(parents=True, exist_ok=True)

    if _fault_log_handle is None:
        try:
            _fault_log_handle = (_crash_log_dir / "native-faults.log").open("a", encoding="utf-8")
            faulthandler.enable(file=_fault_log_handle, all_threads=True)
        except Exception as exc:  # noqa: BLE001 - normal logging is still useful if faulthandler is unavailable.
            log_event(f"Could not enable native crash logging: {exc}", category="crash", level=logging.WARNING)

    if _hooks_installed:
        return
    _hooks_installed = True

    def handle_exception(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            _original_excepthook(exc_type, exc, tb)
            return
        record_crash(
            "Unhandled Python exception",
            exc,
            traceback_text="".join(traceback.format_exception(exc_type, exc, tb)),
        )
        _original_excepthook(exc_type, exc, tb)

    def handle_thread_exception(args: Any) -> None:
        record_crash(
            f"Unhandled thread exception in {getattr(args.thread, 'name', 'thread')}",
            getattr(args, "exc_value", None),
            traceback_text="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )
        if _original_threading_excepthook is not None:
            _original_threading_excepthook(args)

    def handle_unraisable(args: Any) -> None:
        record_crash(
            "Unraisable Python exception",
            getattr(args, "exc_value", None),
            traceback_text="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
            extra={"object": repr(getattr(args, "object", None)), "err_msg": getattr(args, "err_msg", None)},
        )
        if _original_unraisablehook is not None:
            _original_unraisablehook(args)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
    sys.unraisablehook = handle_unraisable


def log_event(
    message: str,
    *,
    category: str = "app",
    level: int = logging.INFO,
    job_id: str = "",
) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.log(level, redact_sensitive_text(message), extra={"category": category, "job_id": job_id})


def get_log_entries(
    *,
    category: str | None = None,
    level: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    limit = max(1, min(1000, limit))
    level = level.upper() if level and level != "all" else level
    with _lock:
        matched = [entry for entry in _entries if _entry_matches(entry, category, level)]
    return [
        {**entry, "message": redact_sensitive_text(entry.get("message", ""))}
        for entry in matched[-limit:]
    ]


def clear_log_entries() -> None:
    with _lock:
        _entries.clear()

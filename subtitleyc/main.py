from __future__ import annotations

import atexit

import json
import logging
import math
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __release__, __version__
from .logs import clear_log_entries, configure_logging, get_log_entries, install_crash_logging, log_event, record_crash
from .security import validate_public_http_url
from .srt import SubtitleCue, adjust_cue_timing, cues_to_ass, cues_to_srt, cues_to_txt, parse_ass, parse_srt
from .videocr_cli import (
    VideOCRCancelled,
    VideOCRCliSettings,
    count_srt_cues,
    find_videocr_cli,
    map_language,
    run_videocr_cli,
)
from .video import VIDEO_EXTENSIONS, StreamingFrameDecoder, VideoToolError, probe_video
from .ytdlp_download import YtDlpDownloadCancelled, download_in_subprocess
from .ytdlp_probe import probe_in_subprocess


def _resource_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _configure_bundled_tools(runtime_root: Path) -> None:
    tools_dir = runtime_root / "tools"
    candidates = [
        tools_dir / "ffmpeg",
        tools_dir / "ffmpeg" / "bin",
        tools_dir / "FFmpeg" / "bin",
    ]
    existing = [str(path) for path in candidates if path.is_dir()]
    if not existing:
        return

    current_parts = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    combined = [part for part in existing if part not in current_parts]
    combined.extend(current_parts)
    os.environ["PATH"] = os.pathsep.join(combined)


APP_NAME = "SubtitleYC"
API_TOKEN = os.environ.get("SUBTITLEYC_API_TOKEN") or secrets.token_urlsafe(32)
SESSION_COOKIE = "subtitleyc_session"
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "testserver"}


def _default_data_dir() -> Path:
    configured = os.environ.get("SUBTITLEYC_DATA_DIR")
    if configured:
        return Path(configured)
    if getattr(sys, "frozen", False):
        for env_name in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env_name)
            if base:
                return Path(base) / APP_NAME / "workspace"
    return RUNTIME_ROOT / "workspace"


APP_ROOT = _resource_root()
RUNTIME_ROOT = _runtime_root()
_configure_bundled_tools(RUNTIME_ROOT)
STATIC_DIR = APP_ROOT / "static"
DATA_DIR = _default_data_dir()
UPLOAD_DIR = DATA_DIR / "uploads"
DOWNLOAD_DIR = DATA_DIR / "downloads"
PREVIEW_DIR = DATA_DIR / "previews"
RESULTS_DIR = DATA_DIR / "results"
VIDEOCR_RUNTIME_DIR = DATA_DIR / "videocr-runtime"
LOG_DIR = DATA_DIR / "logs"
SETTINGS_PATH = DATA_DIR / "settings.json"
LOCAL_PROJECTS_PATH = DATA_DIR / "local-videos.json"
for directory in (
    UPLOAD_DIR,
    DOWNLOAD_DIR,
    PREVIEW_DIR,
    RESULTS_DIR,
    VIDEOCR_RUNTIME_DIR,
    LOG_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)


def _bounded_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        value = default
    return max(min_value, min(max_value, value))


MAX_WORKERS = _bounded_int_env("SUBTITLEYC_MAX_JOBS", 2, 1, 2)
YTDLP_FRAGMENT_DOWNLOADS = _bounded_int_env("SUBTITLEYC_YTDLP_FRAGMENTS", 2, 1, 4)
FRAME_CACHE_LIMIT = _bounded_int_env("SUBTITLEYC_FRAME_CACHE_LIMIT", 360, 60, 2000)
PREVIEW_WARMUP_FRAME_LIMIT = _bounded_int_env("SUBTITLEYC_PREVIEW_WARMUP_LIMIT", 0, 0, 2000)
FRAME_PREVIEW_MAX_WIDTH = _bounded_int_env("SUBTITLEYC_FRAME_PREVIEW_WIDTH", 720, 320, 1920)
MAX_VIDEO_UPLOAD_MB = _bounded_int_env("SUBTITLEYC_MAX_VIDEO_UPLOAD_MB", 20480, 64, 1048576)
MAX_VIDEO_UPLOAD_BYTES = MAX_VIDEO_UPLOAD_MB * 1024 * 1024
MIN_FREE_DISK_MB = _bounded_int_env("SUBTITLEYC_MIN_FREE_DISK_MB", 1024, 128, 102400)
MIN_FREE_DISK_BYTES = MIN_FREE_DISK_MB * 1024 * 1024
SUBTITLE_OUTPUT_FORMATS: dict[str, dict[str, str]] = {
    "srt": {"extension": "srt", "media_type": "application/x-subrip", "label": "SRT"},
    "txt": {"extension": "txt", "media_type": "text/plain; charset=utf-8", "label": "TXT"},
    "ass": {"extension": "ass", "media_type": "text/x-ssa", "label": "ASS"},
}
configure_logging(LOG_DIR)
install_crash_logging(LOG_DIR)
log_event(
    f"SubtitleYC {__release__} starting. data_dir={DATA_DIR} max_jobs={MAX_WORKERS} "
    f"yt_dlp_fragments={YTDLP_FRAGMENT_DOWNLOADS}",
    category="app",
)

app = FastAPI(title="SubtitleYC")


def _request_has_valid_token(request: Request) -> bool:
    supplied = request.headers.get("x-subtitleyc-token") or request.cookies.get(SESSION_COOKIE) or ""
    return bool(supplied) and secrets.compare_digest(supplied, API_TOKEN)


@app.middleware("http")
async def secure_local_requests(request: Request, call_next: Any) -> Response:
    if (request.url.hostname or "").casefold() not in ALLOWED_LOCAL_HOSTS:
        return JSONResponse({"detail": "Invalid local application host."}, status_code=400)

    origin = request.headers.get("origin")
    if origin and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        if origin.rstrip("/").casefold() != expected_origin.casefold():
            return JSONResponse({"detail": "Cross-origin application request rejected."}, status_code=403)

    if request.url.path.startswith("/api/") and not _request_has_valid_token(request):
        return JSONResponse({"detail": "Application session authentication required."}, status_code=401)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self' data: blob: qrc:; script-src 'self' qrc:; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    )
    return response
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
state_lock = threading.Lock()


@dataclass
class VideoSession:
    id: str
    video_path: str
    original_name: str
    source_type: str
    metadata: dict[str, Any]
    preview_path: str
    srt_path: str | None = None
    subtitle_format: str = "srt"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


sessions: dict[str, VideoSession] = {}
jobs: dict[str, Job] = {}
job_cancel_events: dict[str, threading.Event] = {}
job_processes: dict[str, subprocess.Popen[Any]] = {}
frame_decoders: dict[str, StreamingFrameDecoder] = {}
frame_decoder_lock = threading.Lock()


class URLRequest(BaseModel):
    url: str = Field(min_length=3, max_length=8192)
    max_height: int | None = Field(default=None, ge=144, le=4320)
    format_selector: str | None = Field(default=None, max_length=512)
    download_dir: str | None = Field(default=None, max_length=4096)
    download_subtitles: bool = False
    subtitle_languages: str | None = Field(default=None, max_length=256)
    subtitle_source: str | None = Field(default=None, max_length=16)


class LocalVideoOpenRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    keep_copy: bool = False


class SubtitleProbeRequest(BaseModel):
    url: str = Field(min_length=3, max_length=8192)


class FormatProbeRequest(BaseModel):
    url: str = Field(min_length=3, max_length=8192)


class SubtitleDownloadRequest(BaseModel):
    url: str = Field(min_length=3, max_length=8192)
    download_dir: str | None = Field(default=None, max_length=4096)
    output_path: str | None = Field(default=None, max_length=4096)
    subtitle_language: str = Field(min_length=1, max_length=128)
    subtitle_source: str = Field(min_length=1, max_length=16)


class FrontendCrashRequest(BaseModel):
    message: str = Field(default="", max_length=10000)
    source: str = Field(default="frontend", max_length=128)
    stack: str | None = Field(default=None, max_length=50000)
    url: str | None = Field(default=None, max_length=4096)
    user_agent: str | None = Field(default=None, max_length=2048)

class CropRequest(BaseModel):
    x: int
    y: int
    width: int
    height: int


class OCRRequest(BaseModel):
    crop: CropRequest
    language: str = Field(default="eng+chi_sim", min_length=2, max_length=32)
    frame_step: int = Field(default=1, ge=1, le=120)
    min_confidence: int = Field(default=65, ge=0, le=100)
    similarity: float = Field(default=0.72, ge=0.0, le=1.0)
    max_gap_frames: int = Field(default=0, ge=0, le=300)
    merge_gap_seconds: float = Field(default=0.0, ge=0.0, le=10.0)
    psm: int = Field(default=7, ge=3, le=13)
    oem: int = Field(default=3, ge=0, le=3)
    threshold: str = Field(default="subtitle")
    scale: int = Field(default=2, ge=1, le=4)
    start_seconds: float = Field(default=0.0, ge=0.0)
    end_seconds: float | None = Field(default=None, ge=0.0)
    brightness_threshold: int | None = Field(default=None, ge=0, le=255)
    ssim_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    max_image_width: int = Field(default=1280, ge=64, le=4096)
    min_subtitle_duration: float = Field(default=0.04, ge=0.0, le=10.0)
    timing_offset_seconds: float = Field(default=0.0, ge=-10.0, le=10.0)
    snap_to_frame: bool = True
    normalize_chinese: bool = True
    use_fullframe: bool = False
    use_gpu: bool = False
    use_angle_cls: bool = False
    use_server_model: bool = True
    post_processing: bool = False
    use_dual_zone: bool = False
    subtitle_position: str = Field(default="center", max_length=16)
    subtitle_format: str = Field(default="srt", max_length=8)


class AppSettings(BaseModel):
    theme: str = Field(default="dark", pattern="^(dark|light)$")
    default_download_dir: str | None = Field(default=None, max_length=4096)
    default_url_source: str = Field(default="youtube", max_length=16)
    default_resolution: str = Field(default="1080", max_length=16)
    default_language: str = Field(default="eng+chi_sim", min_length=2, max_length=32)
    default_subtitle_format: str = Field(default="srt", max_length=8)
    confidence: int = Field(default=65, ge=0, le=100)
    similarity: int = Field(default=72, ge=0, le=100)
    ssim: int = Field(default=88, ge=0, le=100)
    frames_to_skip: int = Field(default=0, ge=0, le=119)
    merge_gap: float = Field(default=0.0, ge=0.0, le=10.0)
    min_duration: float = Field(default=0.04, ge=0.0, le=10.0)
    timing_offset_frames: float = Field(default=0.0, ge=-300.0, le=300.0)
    snap_to_frame: bool = True
    brightness_threshold: int | None = Field(default=None, ge=0, le=255)
    max_ocr_width: int = Field(default=1280, ge=64, le=4096)
    normalize_chinese: bool = True
    use_server_model: bool = True
    use_fullframe: bool = False
    use_gpu: bool = False
    angle_cls: bool = False
    post_processing: bool = False


class SubtitleCueRequest(BaseModel):
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    text: str = Field(default="", max_length=4000)


class SubtitleEditRequest(BaseModel):
    cues: list[SubtitleCueRequest] = Field(default_factory=list, max_length=10000)
    subtitle_format: str | None = Field(default=None, max_length=8)


class StorageClearRequest(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=16)


class LibraryFileRequest(BaseModel):
    category: str = Field(min_length=1, max_length=32)
    relative_path: str = Field(min_length=1, max_length=4096)


class LibrarySubtitleImportRequest(LibraryFileRequest):
    session_id: str = Field(min_length=1, max_length=64)

def run() -> None:
    import uvicorn

    print(f"Open http://127.0.0.1:8000/?app_token={urllib.parse.quote(API_TOKEN)}")
    uvicorn.run("subtitleyc.main:app", host="127.0.0.1", port=8000, reload=False)


def _job_response(job: Job) -> dict[str, Any]:
    return asdict(job)


def _session_response(session: VideoSession) -> dict[str, Any]:
    payload = asdict(session)
    payload["preview_url"] = f"/api/videos/{session.id}/preview"
    payload["frame_url"] = f"/api/videos/{session.id}/frame"
    payload["video_url"] = f"/api/videos/{session.id}/media"
    if session.srt_path:
        payload["subtitle_url"] = f"/api/videos/{session.id}/subtitle"
        payload["subtitle_format"] = session.subtitle_format
        payload["subtitle_extension"] = _subtitle_extension(session.subtitle_format)
        payload["subtitle_filename"] = _subtitle_filename(session)
        payload["srt_url"] = payload["subtitle_url"]
    return payload




def _normalize_subtitle_format(value: str | None) -> str:
    subtitle_format = (value or "srt").casefold().strip()
    if subtitle_format not in SUBTITLE_OUTPUT_FORMATS:
        allowed = ", ".join(SUBTITLE_OUTPUT_FORMATS)
        raise RuntimeError(f"Unsupported subtitle format: {value or ''}. Choose one of: {allowed}.")
    return subtitle_format


def _subtitle_extension(subtitle_format: str) -> str:
    return SUBTITLE_OUTPUT_FORMATS[_normalize_subtitle_format(subtitle_format)]["extension"]


def _subtitle_media_type(subtitle_format: str) -> str:
    return SUBTITLE_OUTPUT_FORMATS[_normalize_subtitle_format(subtitle_format)]["media_type"]


def _subtitle_label(subtitle_format: str) -> str:
    return SUBTITLE_OUTPUT_FORMATS[_normalize_subtitle_format(subtitle_format)]["label"]


def _subtitle_filename(session: VideoSession) -> str:
    return _subtitle_download_filename(session)


def _write_subtitle_output(
    session_id: str,
    srt_text: str,
    source_srt_path: Path,
    subtitle_format: str,
    title: str,
) -> tuple[Path, int]:
    subtitle_format = _normalize_subtitle_format(subtitle_format)
    if subtitle_format == "srt":
        return source_srt_path, count_srt_cues(srt_text)

    cues = parse_srt(srt_text)
    output_path = _subtitle_storage_path_for(session_id, title, subtitle_format)
    if subtitle_format == "txt":
        content = cues_to_txt(cues)
    else:
        content = cues_to_ass(cues, title=Path(title).stem or "SubtitleYC")
    output_path.write_text(content, encoding="utf-8")
    return output_path, len(cues)


def _normalize_generated_srt_timing(
    srt_text: str,
    session: VideoSession,
    offset_seconds: float,
    snap_to_frame: bool,
) -> str:
    cues = parse_srt(srt_text)
    if not cues:
        return srt_text

    fps = float((session.metadata or {}).get("fps") or 0)
    frame_seconds = 1 / fps if snap_to_frame and fps > 0 else None
    if abs(offset_seconds) < 0.0005 and frame_seconds is None:
        return srt_text

    adjusted = adjust_cue_timing(cues, offset_seconds=offset_seconds, frame_seconds=frame_seconds)
    return cues_to_srt(adjusted)

def _subtitle_source_path(session: VideoSession) -> Path | None:
    readable_path = _subtitle_storage_path(session, "srt")
    if readable_path.is_file():
        return readable_path
    canonical_path = RESULTS_DIR / f"{session.id}.srt"
    if canonical_path.is_file():
        return canonical_path
    if session.srt_path:
        subtitle_path = Path(session.srt_path)
        if subtitle_path.suffix.casefold() == ".srt" and subtitle_path.is_file():
            return subtitle_path
    return None


def _subtitle_cue_payload(cue: SubtitleCue) -> dict[str, Any]:
    return {
        "start_seconds": round(max(0.0, cue.start_seconds), 3),
        "end_seconds": round(max(cue.start_seconds, cue.end_seconds), 3),
        "text": cue.text,
    }


def _subtitle_cues_response(session: VideoSession) -> dict[str, Any]:
    source_path = _subtitle_source_path(session)
    if source_path is None:
        raise HTTPException(status_code=404, detail="Editable subtitle cues were not found")
    srt_text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    cues = parse_srt(srt_text)
    payload = _session_response(session)
    payload.update(
        {
            "cues": [_subtitle_cue_payload(cue) for cue in cues],
            "cue_count": len(cues),
            "subtitle_format": session.subtitle_format,
            "subtitle_filename": _subtitle_filename(session),
            "subtitle_url": f"/api/videos/{session.id}/subtitle",
        }
    )
    return payload



def _subtitle_import_format(filename: str | None) -> str | None:
    suffix = Path(filename or "").suffix.casefold()
    if suffix == ".srt":
        return "srt"
    if suffix in {".ass", ".ssa"}:
        return "ass"
    return None


def _parse_imported_subtitle(filename: str | None, text: str) -> tuple[str, list[SubtitleCue]]:
    import_format = _subtitle_import_format(filename)
    if import_format == "srt":
        cues = parse_srt(text)
    elif import_format == "ass":
        cues = parse_ass(text)
    else:
        srt_cues = parse_srt(text)
        ass_cues = parse_ass(text) if not srt_cues else []
        if srt_cues:
            import_format = "srt"
            cues = srt_cues
        elif ass_cues:
            import_format = "ass"
            cues = ass_cues
        else:
            raise HTTPException(status_code=400, detail="Load a timed .srt, .vtt, .ass, or .ssa subtitle file.")

    cues = sorted((cue for cue in cues if cue.text.strip()), key=lambda cue: (cue.start_seconds, cue.end_seconds))
    if not cues:
        raise HTTPException(status_code=400, detail="No timed subtitle cues were found in that file.")
    return import_format or "srt", cues


def _import_subtitle_cues(session_id: str, filename: str | None, text: str) -> dict[str, Any]:
    session = _get_session(session_id)
    import_format, cues = _parse_imported_subtitle(filename, text)
    source_srt_path = _subtitle_storage_path(session, "srt")
    srt_text = cues_to_srt(cues)
    source_srt_path.write_text(srt_text, encoding="utf-8")
    subtitle_path, cue_count = _write_subtitle_output(
        session.id,
        srt_text,
        source_srt_path,
        import_format,
        session.original_name,
    )
    with state_lock:
        stored = sessions[session.id]
        stored.srt_path = str(subtitle_path)
        stored.subtitle_format = import_format
    log_event(
        f"Imported subtitle file name={Path(filename or 'subtitles').name} count={cue_count} format={import_format}",
        category="subtitle",
    )
    return _subtitle_cues_response(stored)

def _subtitle_cue_from_request(cue: SubtitleCueRequest) -> SubtitleCue:
    start = max(0.0, cue.start_seconds)
    end = max(start + 0.001, cue.end_seconds)
    return SubtitleCue(start_seconds=start, end_seconds=end, text=cue.text.strip())


def _save_subtitle_cues(session_id: str, request: SubtitleEditRequest) -> dict[str, Any]:
    session = _get_session(session_id)
    subtitle_format = _normalize_subtitle_format(request.subtitle_format or session.subtitle_format)
    cues = sorted(
        (cue for cue in (_subtitle_cue_from_request(item) for item in request.cues) if cue.text),
        key=lambda cue: (cue.start_seconds, cue.end_seconds),
    )
    source_srt_path = _subtitle_storage_path(session, "srt")
    srt_text = cues_to_srt(cues)
    source_srt_path.write_text(srt_text, encoding="utf-8")
    subtitle_path, cue_count = _write_subtitle_output(
        session.id,
        srt_text,
        source_srt_path,
        subtitle_format,
        session.original_name,
    )
    with state_lock:
        stored = sessions[session.id]
        stored.srt_path = str(subtitle_path)
        stored.subtitle_format = subtitle_format
    log_event(
        f"Subtitle cues saved count={cue_count} format={subtitle_format} path={subtitle_path}",
        category="subtitle",
    )
    return _subtitle_cues_response(stored)


def _directory_stats(path: Path) -> dict[str, int]:
    total_bytes = 0
    file_count = 0
    if not path.exists():
        return {"bytes": 0, "files": 0}
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total_bytes += item.stat().st_size
                file_count += 1
        except OSError:
            continue
    return {"bytes": total_bytes, "files": file_count}


def _storage_category_specs() -> dict[str, dict[str, Any]]:
    return {
        "downloads": {
            "label": "URL video downloads",
            "description": "Videos and site subtitles downloaded from URL jobs when no custom folder is chosen.",
            "path": DOWNLOAD_DIR,
            "cleanable": True,
        },
        "uploads": {
            "label": "Uploaded video copies",
            "description": "Video files copied into SubtitleYC after using Upload Video.",
            "path": UPLOAD_DIR,
            "cleanable": True,
        },
        "previews": {
            "label": "Preview frame cache",
            "description": "Temporary frames used to keep the preview/editor responsive.",
            "path": PREVIEW_DIR,
            "cleanable": True,
            "visible": False,
        },
        "results": {
            "label": "Saved subtitle outputs",
            "description": "Generated or edited subtitle files saved by SubtitleYC.",
            "path": RESULTS_DIR,
            "cleanable": True,
        },
        "videocr-runtime": {
            "label": "VideOCR runtime files",
            "description": "Temporary files created while OCR jobs are running.",
            "path": VIDEOCR_RUNTIME_DIR,
            "cleanable": True,
            "visible": False,
        },
        "logs": {
            "label": "Logs",
            "description": "App, download, OCR, and error logs.",
            "path": LOG_DIR,
            "cleanable": True,
        },
    }


def _storage_response() -> dict[str, Any]:
    categories: list[dict[str, Any]] = []
    total_bytes = 0
    cleanable_bytes = 0
    for key, spec in _storage_category_specs().items():
        if not spec.get("visible", True):
            continue
        stats = _directory_stats(spec["path"])
        total_bytes += stats["bytes"]
        if spec["cleanable"]:
            cleanable_bytes += stats["bytes"]
        categories.append(
            {
                "key": key,
                "label": spec["label"],
                "description": spec.get("description", ""),
                "path": str(spec["path"]),
                "bytes": stats["bytes"],
                "files": stats["files"],
                "cleanable": spec["cleanable"],
            }
        )
    return {
        "data_dir": str(DATA_DIR),
        "total_bytes": total_bytes,
        "cleanable_bytes": cleanable_bytes,
        "categories": categories,
    }


def _library_entry(category: str, root: Path, path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
        relative_path = path.relative_to(root).as_posix()
    except OSError:
        return None
    return {
        "category": category,
        "relative_path": relative_path,
        "name": path.name,
        "display_name": _library_display_name(path),
        "path": str(path),
        "folder": str(path.parent),
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _library_files(roots: dict[str, Path], extensions: set[str], limit: int = 200) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for category, root in roots.items():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen or not path.is_file() or path.suffix.casefold() not in extensions:
                continue
            seen.add(resolved)
            entry = _library_entry(category, root, path)
            if entry:
                entries.append(entry)

    entries.sort(key=lambda item: item.get("modified_at") or "", reverse=True)
    return entries[:limit]


def _load_local_video_refs() -> list[dict[str, Any]]:
    try:
        raw = json.loads(LOCAL_PROJECTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            refs.append(item)
    return refs


def _save_local_video_refs(refs: list[dict[str, Any]]) -> None:
    try:
        LOCAL_PROJECTS_PATH.write_text(json.dumps(refs[:200], ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log_event(f"Could not save local video references: {exc}", category="library", level=logging.WARNING)


def _remember_local_video(path: Path) -> None:
    try:
        resolved = str(path.resolve(strict=False))
    except OSError:
        resolved = str(path)
    refs = [item for item in _load_local_video_refs() if item.get("path") != resolved]
    refs.insert(0, {"path": resolved, "opened_at": datetime.now(timezone.utc).isoformat()})
    _save_local_video_refs(refs)


def _local_video_entries(limit: int = 200) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _load_local_video_refs():
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or raw_path in seen:
            continue
        seen.add(raw_path)
        path = Path(raw_path)
        if not path.is_file() or path.suffix.casefold() not in VIDEO_EXTENSIONS:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            {
                "category": "local",
                "relative_path": str(path),
                "name": path.name,
                "display_name": _library_display_name(path),
                "path": str(path),
                "folder": str(path.parent),
                "bytes": stat.st_size,
                "modified_at": item.get("opened_at") or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "source_label": "Original file",
            }
        )
        if len(entries) >= limit:
            break
    return entries


def _validate_remote_url(value: str) -> str:
    return validate_public_http_url(value)


def _ensure_free_disk(path: Path, required_bytes: int = 0) -> None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as exc:
        raise RuntimeError(f"Could not check free disk space for {path}.") from exc
    needed = max(0, int(required_bytes)) + MIN_FREE_DISK_BYTES
    if free < needed:
        needed_gb = needed / (1024 ** 3)
        free_gb = free / (1024 ** 3)
        raise RuntimeError(
            f"Not enough free space. SubtitleYC needs {needed_gb:.1f} GB available "
            f"but only {free_gb:.1f} GB is free."
        )

def _resolve_external_video_path(raw_path: str) -> Path:
    path = Path(os.path.expandvars(raw_path or "")).expanduser()
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Video file does not exist: {path}") from exc
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Video path is not a file: {path}")
    if path.suffix.casefold() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose a supported video file.")
    return path


def _copy_video_to_uploads(source: Path) -> Path:
    source_size = source.stat().st_size
    if source_size > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Keeping a copied video is limited to {MAX_VIDEO_UPLOAD_MB} MB. Open it without keeping a copy instead.",
        )
    _ensure_free_disk(UPLOAD_DIR, source_size)
    suffix = source.suffix.casefold() if source.suffix else ".mp4"
    stem = _clean_filename_stem(source.stem, "uploaded video")
    target = _unique_file_path(UPLOAD_DIR, stem, suffix)
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not copy video into SubtitleYC storage: {exc}") from exc
    return target

def _library_response() -> dict[str, Any]:
    videos = [*_local_video_entries(), *_library_files({"uploads": UPLOAD_DIR, "downloads": DOWNLOAD_DIR}, VIDEO_EXTENSIONS)]
    videos.sort(key=lambda item: item.get("modified_at") or "", reverse=True)
    return {
        "data_dir": str(DATA_DIR),
        "videos": videos[:200],
        "subtitles": _library_files({"results": RESULTS_DIR, "downloads": DOWNLOAD_DIR}, DOWNLOADED_SUBTITLE_EXTENSIONS),
    }

def _resolve_library_file(request: LibraryFileRequest, roots: dict[str, Path], extensions: set[str]) -> Path:
    category = request.category.strip().casefold()
    root = roots.get(category)
    if root is None:
        raise HTTPException(status_code=400, detail="Unknown library category.")
    base = root.resolve()
    candidate = (base / request.relative_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Library path is outside the app workspace.") from exc
    if not candidate.is_file() or candidate.suffix.casefold() not in extensions:
        raise HTTPException(status_code=404, detail="Library file was not found.")
    return candidate


def _has_active_jobs() -> bool:
    with state_lock:
        return any(job.status in {"queued", "running"} for job in jobs.values())


def _ensure_data_child(path: Path) -> Path:
    resolved = path.resolve()
    data_root = DATA_DIR.resolve()
    if resolved == data_root or not resolved.is_relative_to(data_root):
        raise RuntimeError(f"Refusing to clear outside app data folder: {resolved}")
    return resolved


def _safe_clear_directory_contents(path: Path) -> None:
    resolved = _ensure_data_child(path)
    if not resolved.exists():
        resolved.mkdir(parents=True, exist_ok=True)
        return
    for item in resolved.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except OSError as exc:
            log_event(f"Could not clear storage item {item}: {exc}", category="storage", level=logging.WARNING)
    resolved.mkdir(parents=True, exist_ok=True)


def _clear_log_storage() -> None:
    clear_log_entries()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for path in LOG_DIR.glob("subtitleyc.log*"):
        try:
            if path.name == "subtitleyc.log":
                path.write_text("", encoding="utf-8")
            else:
                path.unlink()
        except OSError as exc:
            log_event(f"Could not clear log file {path}: {exc}", category="storage", level=logging.WARNING)


def _clear_storage_categories(keys: list[str]) -> dict[str, Any]:
    specs = _storage_category_specs()
    requested = [key for key in dict.fromkeys(keys) if key]
    if not requested:
        raise HTTPException(status_code=400, detail="Choose at least one storage category to clear")
    unknown = [key for key in requested if key not in specs]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown storage category: {', '.join(unknown)}")
    blocked = [key for key in requested if not specs[key]["cleanable"]]
    if blocked:
        raise HTTPException(status_code=400, detail=f"Storage category cannot be cleared: {', '.join(blocked)}")
    if _has_active_jobs() and any(key != "logs" for key in requested):
        raise HTTPException(status_code=409, detail="Stop active jobs before clearing runtime storage")

    before = _storage_response()
    if "previews" in requested:
        _close_frame_decoders()
    for key in requested:
        if key == "logs":
            _clear_log_storage()
        else:
            _safe_clear_directory_contents(specs[key]["path"])
        log_event(f"Storage category cleared: {key}", category="storage")
    after = _storage_response()
    return {"cleared": requested, "before": before, "storage": after}


class JobCancelled(RuntimeError):
    pass


def _bundled_videocr_metadata() -> dict[str, Any]:
    metadata_path = RUNTIME_ROOT / "tools" / "videocr-build.json"
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_settings() -> dict[str, Any]:
    defaults = AppSettings().model_dump()
    metadata = _bundled_videocr_metadata()
    if metadata.get("gpu_default") is True:
        defaults["use_gpu"] = True
    return defaults


def _settings_response(settings: AppSettings | None = None) -> dict[str, Any]:
    current = settings.model_dump() if settings else _load_settings().model_dump()
    return {"settings": current, "defaults": _default_settings()}


def _load_settings() -> AppSettings:
    payload: dict[str, Any] = {}
    if SETTINGS_PATH.is_file():
        try:
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            log_event("Could not read settings file; using defaults", category="settings", level=logging.WARNING)
    return AppSettings.model_validate({**_default_settings(), **payload})


def _save_settings(settings: AppSettings) -> AppSettings:
    SETTINGS_PATH.write_text(json.dumps(settings.model_dump(), indent=2), encoding="utf-8")
    log_event("Settings saved", category="settings")
    return settings


def _job_cancel_event(job_id: str) -> threading.Event:
    with state_lock:
        event = job_cancel_events.get(job_id)
        if event is None:
            event = threading.Event()
            job_cancel_events[job_id] = event
        return event


def _cancel_requested(job_id: str) -> bool:
    with state_lock:
        event = job_cancel_events.get(job_id)
    return bool(event and event.is_set())


def _raise_if_cancelled(job_id: str) -> None:
    if _cancel_requested(job_id):
        raise JobCancelled("Job was cancelled.")


def _register_job_process(job_id: str, process: subprocess.Popen[Any]) -> None:
    with state_lock:
        job_processes[job_id] = process


def _unregister_job_process(job_id: str) -> None:
    with state_lock:
        job_processes.pop(job_id, None)


def _stop_registered_process(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _mark_job_cancelled(job_id: str, message: str = "Cancelled") -> None:
    _set_job(job_id, status="cancelled", message=message)


def _set_job(job_id: str, **updates: Any) -> None:
    log_details: tuple[int, str, str, str] | None = None
    with state_lock:
        job = jobs[job_id]
        old_status = job.status
        for key, value in updates.items():
            setattr(job, key, value)
        if "status" in updates and job.status != old_status:
            level = logging.ERROR if job.status == "failed" else logging.INFO
            message = str(updates.get("error") or updates.get("message") or job.message)
            log_details = (level, job.kind, job.id, f"{job.kind} job {job.status}: {message}")
    if log_details:
        level, category, logged_job_id, message = log_details
        log_event(message, category=category, level=level, job_id=logged_job_id)


def _create_job(kind: str) -> Job:
    job = Job(id=uuid.uuid4().hex, kind=kind)
    with state_lock:
        jobs[job.id] = job
    log_event(f"{kind} job queued", category=kind, job_id=job.id)
    return job

def _submit_job(job: Job, func: Any, *args: Any) -> None:
    future = executor.submit(func, *args)

    def handle_done(done_future: Any) -> None:
        try:
            done_future.result()
        except BaseException as exc:  # noqa: BLE001 - unexpected worker exits should be visible.
            record_crash(
                f"Unhandled {job.kind} worker crash",
                exc,
                category=job.kind,
                job_id=job.id,
                extra={"job_kind": job.kind},
            )
            if not _cancel_requested(job.id):
                _set_job(job.id, status="failed", error=str(exc), message=f"{job.kind} crashed")

    future.add_done_callback(handle_done)

def _sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned[:120] or "video"


_WINDOWS_RESERVED_FILE_STEMS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _clean_filename_stem(value: str | Path | None, fallback: str = "file") -> str:
    stem = Path(str(value or fallback)).stem if value is not None else fallback
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", stem)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in _WINDOWS_RESERVED_FILE_STEMS:
        cleaned = f"{cleaned} file"
    return cleaned[:150].rstrip(" ._-") or fallback


def _safe_filename(stem: str, suffix: str) -> str:
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{_clean_filename_stem(stem)}{extension.casefold()}"


def _unique_file_path(directory: Path, stem: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    base = _clean_filename_stem(stem)
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    extension = extension.casefold()
    for index in range(1, 1000):
        candidate_stem = base if index == 1 else f"{base} ({index})"
        candidate = directory / f"{candidate_stem}{extension}"
        if not candidate.exists():
            return candidate
    return directory / f"{base} - {uuid.uuid4().hex[:8]}{extension}"


def _subtitle_storage_stem(session_id: str, title: str) -> str:
    return f"{_clean_filename_stem(title, 'subtitles')} - subtitles - {session_id[:8]}"


def _subtitle_storage_path_for(session_id: str, title: str, subtitle_format: str) -> Path:
    return RESULTS_DIR / _safe_filename(_subtitle_storage_stem(session_id, title), _subtitle_extension(subtitle_format))


def _subtitle_storage_path(session: VideoSession, subtitle_format: str) -> Path:
    return _subtitle_storage_path_for(session.id, session.original_name, subtitle_format)


def _subtitle_download_filename(session: VideoSession, subtitle_format: str | None = None) -> str:
    return _safe_filename(f"{_clean_filename_stem(session.original_name, 'subtitles')} - subtitles", _subtitle_extension(subtitle_format or session.subtitle_format))


def _library_display_name(path: Path) -> str:
    stem = path.stem
    suffix = path.suffix
    stem = re.sub(r"^[0-9a-f]{32}_", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r" - subtitles - [0-9a-f]{8}$", " - subtitles", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\.f\d+$", "", stem, flags=re.IGNORECASE)
    if " " not in stem and "_" in stem:
        stem = stem.replace("_", " ")
    return _safe_filename(stem, suffix or path.suffix)


YT_DLP_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}
BILIBILI_FORMATS_BY_HEIGHT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1080, ("30080+30280", "30080+30232", "30080+bestaudio")),
    (720, ("30064+30280", "30064+30232", "30064+bestaudio")),
    (480, ("30032+30280", "30032+30232", "30032+bestaudio")),
    (360, ("30016+30280", "30016+30232", "30016+bestaudio")),
)
DOWNLOADED_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


def _is_bilibili_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    host = host.casefold().strip(".")
    return host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com")


def _bilibili_format_fallbacks(max_height: int | None) -> list[str]:
    height_limit = max_height if max_height is not None else BILIBILI_FORMATS_BY_HEIGHT[0][0]
    formats: list[str] = []
    for height, height_formats in BILIBILI_FORMATS_BY_HEIGHT:
        if height <= height_limit:
            formats.extend(height_formats)
    return formats


def _download_format(max_height: int | None, url: str | None = None) -> str:
    if max_height:
        default_format = (
            f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"
        )
    else:
        default_format = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
    if _is_bilibili_url(url):
        return "/".join([*_bilibili_format_fallbacks(max_height), default_format])
    return default_format


def _download_headers(url: str | None) -> dict[str, str]:
    headers = dict(YT_DLP_BROWSER_HEADERS)
    if _is_bilibili_url(url):
        headers.update(
            {
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )
    return headers


def _download_sort(max_height: int | None) -> list[str]:
    if max_height:
        return [f"res:{max_height}", "ext:mp4:m4a", "codec:h264:aac"]
    return ["res", "ext:mp4:m4a", "codec:h264:aac"]


def _resolve_download_dir(job_id: str, requested_dir: str | None) -> Path:
    requested = (requested_dir or "").strip()
    if requested:
        output_dir = Path(os.path.expandvars(requested)).expanduser()
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
    else:
        output_dir = DOWNLOAD_DIR / job_id

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _ensure_free_disk(output_dir)
    except OSError as exc:
        raise RuntimeError(f"Could not create download folder: {output_dir}") from exc
    if not output_dir.is_dir():
        raise RuntimeError(f"Download location is not a folder: {output_dir}")
    return output_dir


def _resolve_subtitle_output_path(requested_path: str | None) -> Path | None:
    requested = (requested_path or "").strip()
    if not requested:
        return None
    output_path = Path(os.path.expandvars(requested)).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    if output_path.suffix.casefold() != ".srt":
        output_path = output_path.with_suffix(".srt")
    if output_path.exists() and output_path.is_dir():
        raise RuntimeError(f"Subtitle save location is a folder: {output_path}")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Could not create subtitle save folder: {output_path.parent}") from exc
    return output_path


def _downloaded_video_from_info(info: Any) -> Path | None:
    if not isinstance(info, dict):
        return None

    def candidate(value: Any) -> Path | None:
        if not isinstance(value, str):
            return None
        path = Path(value)
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            return path
        return None

    for item in info.get("requested_downloads") or []:
        if not isinstance(item, dict):
            continue
        for key in ("filepath", "filename", "_filename"):
            path = candidate(item.get(key))
            if path:
                return path

    for key in ("filepath", "filename", "_filename"):
        path = candidate(info.get(key))
        if path:
            return path
    return None


def _newest_video_file_after(directory: Path, started_at: float) -> Path | None:
    if not directory.is_dir():
        return None
    candidates: list[Path] = []
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.casefold() not in VIDEO_EXTENSIONS:
            continue
        try:
            if path.stat().st_mtime >= started_at - 5:
                candidates.append(path)
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)

def _subtitle_language_list(value: str | None) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return ["en"]
    languages = [part.strip() for part in raw.split(",") if part.strip()]
    return languages or ["en"]


def _subtitle_language_matches(language: str, requested: str) -> bool:
    requested = requested.strip()
    if not requested:
        return False
    if requested == "all" or language.casefold() == requested.casefold():
        return True
    try:
        return re.fullmatch(requested, language, flags=re.IGNORECASE) is not None
    except re.error:
        return False


def _first_matching_subtitle_language(available: Any, requested_languages: list[str]) -> str | None:
    if not isinstance(available, dict) or not available:
        return None
    for requested in requested_languages:
        if requested in available:
            return requested
    for requested in requested_languages:
        for language in available:
            if _subtitle_language_matches(str(language), requested):
                return str(language)
    return None


_SUBTITLE_LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "zh": "Chinese",
    "zh-cn": "Chinese Simplified",
    "zh-hans": "Chinese Simplified",
    "zh-hant": "Chinese Traditional",
    "zh-tw": "Chinese Traditional",
    "ja": "Japanese",
    "jp": "Japanese",
    "ko": "Korean",
}


def _subtitle_language_label(language: str) -> str:
    normalized = language.strip().casefold()
    if not normalized:
        return "Subtitle"
    if normalized in _SUBTITLE_LANGUAGE_LABELS:
        return _SUBTITLE_LANGUAGE_LABELS[normalized]
    if normalized.startswith("en"):
        return "English"
    if normalized.startswith("zh"):
        return "Chinese"
    return language


def _subtitle_format_list(entries: Any) -> list[str]:
    formats: list[str] = []
    if not isinstance(entries, list):
        return formats
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        extension = str(entry.get("ext") or "").strip()
        if extension and extension not in formats:
            formats.append(extension)
    return formats


def _subtitle_track_payload(source: str, language: str, entries: Any) -> dict[str, Any]:
    formats = _subtitle_format_list(entries)
    label = _subtitle_language_label(language)
    source_label = "Auto" if source == "auto" else "Manual"
    format_label = f" - {', '.join(formats[:3])}" if formats else ""
    return {
        "id": f"{source}:{language}",
        "source": source,
        "language": language,
        "label": label,
        "formats": formats,
        "display": f"{label} ({language}) - {source_label}{format_label}",
    }


def _subtitle_tracks_from_info(info: dict[str, Any]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for source, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        available = info.get(key)
        if not isinstance(available, dict):
            continue
        for raw_language, entries in sorted(available.items(), key=lambda item: str(item[0]).casefold()):
            language = str(raw_language)
            tracks.append(_subtitle_track_payload(source, language, entries))
    return tracks



def _media_size_label(format_info: dict[str, Any]) -> str:
    size = format_info.get("filesize") or format_info.get("filesize_approx") or 0
    try:
        size = float(size)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return ""
    units = ("B", "KiB", "MiB", "GiB")
    value = size
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"


def _format_tbr_label(format_info: dict[str, Any]) -> str:
    tbr = format_info.get("tbr")
    try:
        tbr = float(tbr)
    except (TypeError, ValueError):
        return ""
    if tbr <= 0:
        return ""
    return f"{tbr / 1000:.2f} Mbps" if tbr >= 1000 else f"{tbr:.0f} kbps"


def _format_resolution_label(format_info: dict[str, Any]) -> str:
    resolution = str(format_info.get("resolution") or "").strip()
    if resolution and resolution != "audio only":
        return resolution
    width = format_info.get("width")
    height = format_info.get("height")
    if width and height:
        return f"{width}x{height}"
    if height:
        return f"{height}p"
    return "video"


def _format_entry_payload(format_info: dict[str, Any]) -> dict[str, Any] | None:
    format_id = str(format_info.get("format_id") or "").strip()
    if not format_id:
        return None
    vcodec = str(format_info.get("vcodec") or "").strip()
    acodec = str(format_info.get("acodec") or "").strip()
    has_video = bool(vcodec and vcodec != "none")
    has_audio = bool(acodec and acodec != "none")
    if not has_video:
        return None

    selector = format_id if has_audio else f"{format_id}+bestaudio/best"
    ext = str(format_info.get("ext") or "").strip()
    fps = format_info.get("fps")
    dynamic_range = str(format_info.get("dynamic_range") or "").strip()
    note = str(format_info.get("format_note") or "").strip()
    pieces = [_format_resolution_label(format_info)]
    if fps:
        pieces.append(f"{fps} fps")
    if ext:
        pieces.append(ext)
    if dynamic_range and dynamic_range.upper() != "SDR":
        pieces.append(dynamic_range)
    tbr = _format_tbr_label(format_info)
    if tbr:
        pieces.append(tbr)
    size = _media_size_label(format_info)
    if size:
        pieces.append(size)
    if not has_audio:
        pieces.append("+ best audio")
    if note and note not in pieces:
        pieces.append(note)

    height = format_info.get("height") or 0
    try:
        height = int(height)
    except (TypeError, ValueError):
        height = 0
    try:
        tbr_sort = float(format_info.get("tbr") or 0)
    except (TypeError, ValueError):
        tbr_sort = 0.0

    return {
        "id": format_id,
        "selector": selector,
        "display": f"{format_id} - {' | '.join(str(piece) for piece in pieces if piece)}",
        "ext": ext,
        "height": height,
        "width": format_info.get("width") or 0,
        "fps": fps or 0,
        "tbr": tbr_sort,
        "has_audio": has_audio,
    }



def _probe_ytdlp_formats(url: str) -> dict[str, Any]:
    url = _validate_remote_url(url)
    try:
        info = probe_in_subprocess("formats", url)
    except RuntimeError as exc:
        raise RuntimeError(f"Could not check video formats: {exc}") from exc

    formats: list[dict[str, Any]] = []
    seen_selectors: set[str] = set()
    for item in info.get("formats") or []:
        if not isinstance(item, dict):
            continue
        payload = _format_entry_payload(item)
        if not payload or payload["selector"] in seen_selectors:
            continue
        seen_selectors.add(payload["selector"])
        formats.append(payload)

    formats.sort(
        key=lambda item: (
            int(item.get("height") or 0),
            float(item.get("tbr") or 0),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return {
        "title": str(info.get("title") or ""),
        "format_count": len(formats),
        "formats": formats,
    }

def _probe_ytdlp_subtitles(url: str) -> dict[str, Any]:
    url = _validate_remote_url(url)
    try:
        info = probe_in_subprocess("subtitles", url)
    except RuntimeError as exc:
        raise RuntimeError(f"Could not check site subtitles: {exc}") from exc

    tracks = _subtitle_tracks_from_info(info)
    return {
        "title": str(info.get("title") or ""),
        "track_count": len(tracks),
        "tracks": tracks,
    }

def _choose_ytdlp_subtitle_source(url: str, requested_languages: list[str], job_id: str) -> tuple[str | None, list[str]]:
    fallback_languages = requested_languages[:1] or ["en"]
    try:
        info = probe_in_subprocess("subtitles", url)
    except RuntimeError as exc:
        log_event(
            f"Could not inspect site subtitles before download: {exc}",
            category="download",
            level=logging.WARNING,
            job_id=job_id,
        )
        return "manual", fallback_languages

    manual_language = _first_matching_subtitle_language(info.get("subtitles"), requested_languages)
    if manual_language:
        log_event(f"Using manual site subtitles language={manual_language}", category="download", job_id=job_id)
        return "manual", [manual_language]

    automatic_language = _first_matching_subtitle_language(info.get("automatic_captions"), requested_languages)
    if automatic_language:
        log_event(f"Using auto site subtitles language={automatic_language}", category="download", job_id=job_id)
        return "auto", [automatic_language]

    log_event("No matching site subtitle language was found", category="download", level=logging.WARNING, job_id=job_id)
    return None, fallback_languages
def _subtitle_language_rank(path: Path, languages: list[str]) -> int:
    name = path.name.casefold()
    for index, language in enumerate(languages):
        prefix = language.strip().rstrip(".*").casefold()
        if prefix and f".{prefix}" in name:
            return index
    return len(languages)


def _subtitle_extension_rank(path: Path) -> int:
    return {".srt": 0, ".ass": 1, ".ssa": 2, ".vtt": 3}.get(path.suffix.casefold(), 9)


def _downloaded_subtitle_files(video_path: Path, output_dir: Path, started_at: float, languages: list[str]) -> list[Path]:
    if not output_dir.is_dir():
        return []
    video_stem = video_path.stem.casefold()
    candidates: list[Path] = []
    for path in output_dir.iterdir():
        if not path.is_file() or path.suffix.casefold() not in DOWNLOADED_SUBTITLE_EXTENSIONS:
            continue
        try:
            if path.stat().st_mtime < started_at - 5:
                continue
        except OSError:
            continue
        stem = path.stem.casefold()
        if stem == video_stem or stem.startswith(f"{video_stem}."):
            candidates.append(path)

    candidates.sort(key=lambda path: (_subtitle_language_rank(path, languages), _subtitle_extension_rank(path), -path.stat().st_mtime))
    return candidates


def _downloaded_subtitle_file(video_path: Path, output_dir: Path, started_at: float, languages: list[str]) -> Path | None:
    candidates = _downloaded_subtitle_files(video_path, output_dir, started_at, languages)
    return candidates[0] if candidates else None


def _cleanup_extra_downloaded_subtitles(video_path: Path, output_dir: Path, started_at: float, languages: list[str], keep: Path) -> None:
    try:
        keep_resolved = keep.resolve()
    except OSError:
        keep_resolved = keep
    for path in _downloaded_subtitle_files(video_path, output_dir, started_at, languages):
        try:
            if path.resolve() == keep_resolved:
                continue
            path.unlink(missing_ok=True)
            log_event(f"Removed extra downloaded subtitle sidecar {path.name}", category="download")
        except OSError:
            continue


def _attach_downloaded_subtitle(session: VideoSession, subtitle_path: Path, job_id: str) -> dict[str, Any] | None:
    try:
        text = subtitle_path.read_text(encoding="utf-8-sig")
        payload = _import_subtitle_cues(session.id, subtitle_path.name, text)
        log_event(f"Attached downloaded subtitle file {subtitle_path.name}", category="download", job_id=job_id)
        return payload
    except Exception as exc:  # noqa: BLE001 - keep the video usable even if subtitle import fails.
        log_event(
            f"Downloaded subtitle import failed for {subtitle_path}: {exc}",
            category="download",
            level=logging.WARNING,
            job_id=job_id,
        )
        return None

def _video_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _log_ytdlp_worker_messages(result: dict[str, Any], job_id: str) -> None:
    messages = result.get("messages")
    if not isinstance(messages, list):
        return
    for raw_message in messages[-16:]:
        message = str(raw_message).strip()
        if message.startswith("WARNING:"):
            log_event(message, category="download", level=logging.WARNING, job_id=job_id)
        elif message.startswith("ERROR:"):
            log_event(message, category="download", level=logging.ERROR, job_id=job_id)

def _prepare_session(video_path: Path, original_name: str, source_type: str) -> VideoSession:
    session_id = uuid.uuid4().hex
    metadata = probe_video(video_path)
    preview_path = PREVIEW_DIR / f"{session_id}.jpg"
    default_subtitle_format = _normalize_subtitle_format(_load_settings().default_subtitle_format)
    session = VideoSession(
        id=session_id,
        video_path=str(video_path),
        original_name=original_name,
        source_type=source_type,
        metadata=metadata,
        preview_path=str(preview_path),
        subtitle_format=default_subtitle_format,
    )
    with state_lock:
        sessions[session.id] = session
    return session


def _get_session(session_id: str) -> VideoSession:
    with state_lock:
        session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Video session not found")
    return session


def _get_frame_decoder(session: VideoSession) -> StreamingFrameDecoder:
    video_path = Path(session.video_path)
    with frame_decoder_lock:
        decoder = frame_decoders.get(session.id)
        if decoder and decoder.video_path == video_path:
            return decoder
        if decoder:
            decoder.close()
        decoder = StreamingFrameDecoder(
            video_path,
            session.metadata,
            PREVIEW_DIR / session.id,
            cache_limit=FRAME_CACHE_LIMIT,
            max_preview_width=FRAME_PREVIEW_MAX_WIDTH,
        )
        frame_decoders[session.id] = decoder
        return decoder


def _close_frame_decoders() -> None:
    with frame_decoder_lock:
        decoders = list(frame_decoders.values())
        frame_decoders.clear()
    for decoder in decoders:
        decoder.close()


atexit.register(_close_frame_decoders)


def _preview_warmup_indexes(frame_count: int, limit: int) -> list[int]:
    total = max(0, int(frame_count or 0))
    if total <= 0 or limit <= 0:
        return []
    if total <= limit:
        return list(range(total))
    stride = max(1, math.ceil(total / limit))
    indexes = list(range(0, total, stride))[:limit]
    last = total - 1
    if indexes and indexes[-1] != last:
        indexes[-1] = last
    return indexes


def _run_preview_cache_job(job_id: str, session_id: str) -> None:
    try:
        _raise_if_cancelled(job_id)
        session = _get_session(session_id)
        decoder = _get_frame_decoder(session)
        frame_count = int((session.metadata or {}).get("frame_count") or decoder.frame_count or 0)
        indexes = _preview_warmup_indexes(frame_count, PREVIEW_WARMUP_FRAME_LIMIT)
        if not indexes:
            _set_job(job_id, status="complete", progress=1.0, message="No preview frames to cache", result={"cached_frames": 0})
            return

        limited = frame_count > len(indexes)
        started = time.monotonic()
        _set_job(job_id, status="running", progress=0.01, message=f"Warming {len(indexes)} preview frames")
        for position, frame_index in enumerate(indexes, start=1):
            _raise_if_cancelled(job_id)
            decoder.get_frame_bytes(frame_index)
            if position == len(indexes) or position % 12 == 0:
                _set_job(
                    job_id,
                    progress=min(0.99, 0.01 + (position / len(indexes)) * 0.98),
                    message=f"Warming preview frame {position}/{len(indexes)}",
                )

        elapsed = time.monotonic() - started
        message = "Preview frames warmed" if not limited else f"Preview cache warmed ({len(indexes)} sampled frames)"
        _set_job(
            job_id,
            status="complete",
            progress=1.0,
            message=message,
            result={
                "cached_frames": len(indexes),
                "total_frames": frame_count,
                "limited": limited,
                "elapsed_seconds": round(elapsed, 2),
            },
        )
    except JobCancelled:
        _mark_job_cancelled(job_id, "Preview cache cancelled")
    except Exception as exc:  # noqa: BLE001 - surface preview cache failures in the activity row.
        log_event(f"Preview cache failed: {exc}", category="preview", level=logging.ERROR, job_id=job_id)
        _set_job(job_id, status="failed", progress=0.0, error=str(exc), message="Preview cache failed")



def _newest_subtitle_file_after(output_dir: Path, started_at: float, languages: list[str]) -> Path | None:
    if not output_dir.is_dir():
        return None
    candidates: list[Path] = []
    for path in output_dir.iterdir():
        if not path.is_file() or path.suffix.casefold() not in DOWNLOADED_SUBTITLE_EXTENSIONS:
            continue
        try:
            if path.stat().st_mtime < started_at - 5:
                continue
        except OSError:
            continue
        candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda path: (_subtitle_language_rank(path, languages), _subtitle_extension_rank(path), -path.stat().st_mtime))
    return candidates[0]


def _download_site_subtitle(
    job_id: str,
    url: str,
    download_dir: str | None,
    output_path: str | None,
    subtitle_language: str,
    subtitle_source: str,
) -> None:
    try:
        _raise_if_cancelled(job_id)
        url = _validate_remote_url(url)

        selected_source = subtitle_source.strip().casefold()
        if selected_source not in {"manual", "auto"}:
            raise RuntimeError("Choose a manual or auto subtitle track first.")
        selected_language = subtitle_language.strip()
        if not selected_language:
            raise RuntimeError("Choose a subtitle language first.")

        target_path = _resolve_subtitle_output_path(output_path)
        output_dir = target_path.parent if target_path else _resolve_download_dir(job_id, download_dir)
        started_at = time.time()
        _set_job(job_id, status="running", progress=0.05, message=f"Downloading {selected_language} subtitle")
        log_event(
            f"Starting subtitle-only download source={selected_source} language={selected_language} output_dir={output_dir}",
            category="download",
            job_id=job_id,
        )

        def hook(event: dict[str, Any]) -> None:
            _ensure_free_disk(output_dir)
            _raise_if_cancelled(job_id)
            status = event.get("status")
            if status == "downloading":
                total = event.get("total_bytes") or 0
                downloaded = event.get("downloaded_bytes") or 0
                ratio = downloaded / total if total else 0
                _set_job(job_id, progress=min(0.85, 0.15 + ratio * 0.65), message="Downloading subtitle")
            elif status == "finished":
                _set_job(job_id, progress=0.9, message="Preparing subtitle file")

        options = {
            "skip_download": True,
            "writesubtitles": selected_source == "manual",
            "writeautomaticsub": selected_source == "auto",
            "subtitleslangs": [selected_language],
            "subtitlesformat": "srt/vtt/best",
            "convertsubtitles": "srt",
            "noplaylist": True,
            "outtmpl": str(output_dir / "%(title).180B - %(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": False,
            "retries": 3,
            "fragment_retries": 3,
            "windowsfilenames": True,
            "proxy": "",
            "restrictfilenames": False,
            "http_headers": _download_headers(url),
        }
        try:
            worker_result = download_in_subprocess(
                url,
                options,
                progress=hook,
                cancel_event=_job_cancel_event(job_id),
                process_callback=lambda process: _register_job_process(job_id, process),
                fault_log_path=LOG_DIR / "crashes" / "yt-dlp-worker-native.log",
            )
        finally:
            _unregister_job_process(job_id)
        _raise_if_cancelled(job_id)
        _log_ytdlp_worker_messages(worker_result, job_id)

        subtitle_path = _newest_subtitle_file_after(output_dir, started_at, [selected_language])
        if subtitle_path is None:
            raise RuntimeError("yt-dlp finished but no subtitle file was found.")

        final_path = subtitle_path
        if target_path:
            if subtitle_path.resolve(strict=False) != target_path.resolve(strict=False):
                if target_path.exists():
                    target_path.unlink()
                shutil.move(str(subtitle_path), str(target_path))
            final_path = target_path

        log_event(f"Downloaded subtitle to {final_path}", category="download", job_id=job_id)
        _set_job(
            job_id,
            status="complete",
            progress=1.0,
            message="Subtitle ready",
            result={
                "path": str(final_path),
                "filename": final_path.name,
                "download_dir": str(final_path.parent),
                "subtitle_language": selected_language,
                "subtitle_source": selected_source,
            },
        )
    except (JobCancelled, YtDlpDownloadCancelled):
        log_event("Subtitle download cancelled", category="download", job_id=job_id)
        _mark_job_cancelled(job_id)
    except Exception as exc:
        if _cancel_requested(job_id):
            log_event("Subtitle download cancelled", category="download", job_id=job_id)
            _mark_job_cancelled(job_id)
            return
        message = str(exc)
        record_crash(
            "Subtitle download failed",
            exc,
            category="download",
            job_id=job_id,
            extra={"url": url, "tail": message[-2000:]},
        )
        log_event(f"Subtitle download failed: {message}", category="download", level=logging.ERROR, job_id=job_id)
        _set_job(job_id, status="failed", error=message, message="Subtitle download failed")

def _download_with_ytdlp(
    job_id: str,
    url: str,
    max_height: int | None,
    format_selector: str | None = None,
    download_dir: str | None = None,
    download_subtitles: bool = False,
    subtitle_languages: str | None = None,
    subtitle_source: str | None = None,
) -> None:
    try:
        _raise_if_cancelled(job_id)
        url = _validate_remote_url(url)

        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is required for yt-dlp downloads and format merging.")

        selected_format = (format_selector or "").strip()
        resolution_label = "selected format" if selected_format else (f"{max_height}p" if max_height else "best available")
        subtitle_langs = _subtitle_language_list(subtitle_languages)
        requested_subtitle_source = (subtitle_source or "").strip().casefold()
        subtitle_note = " + site subtitles" if download_subtitles else ""
        _set_job(job_id, status="running", progress=0.02, message=f"Starting yt-dlp ({resolution_label}{subtitle_note})")
        output_dir = _resolve_download_dir(job_id, download_dir)
        download_host = urllib.parse.urlparse(url).hostname or "unknown"
        log_event(
            f"Starting yt-dlp host={download_host} resolution={resolution_label} output_dir={output_dir} subtitles={download_subtitles} langs={','.join(subtitle_langs)}",
            category="download",
            job_id=job_id,
        )

        def hook(event: dict[str, Any]) -> None:
            _ensure_free_disk(output_dir)
            _raise_if_cancelled(job_id)
            if event.get("status") == "downloading":
                total = event.get("total_bytes") or 0
                downloaded = event.get("downloaded_bytes") or 0
                ratio = downloaded / total if total else 0
                speed = event.get("speed") or 0
                speed_text = f" at {speed / 1024 / 1024:.1f} MB/s" if speed else ""
                _set_job(
                    job_id,
                    progress=min(0.88, 0.05 + ratio * 0.75),
                    message=f"Downloading video{speed_text}",
                )
            elif event.get("status") == "finished":
                _set_job(job_id, progress=0.9, message="Preparing downloaded video")

        options = {
            "format": selected_format or _download_format(max_height, url),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "outtmpl": str(output_dir / "%(title).180B - %(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": False,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": YTDLP_FRAGMENT_DOWNLOADS,
            "windowsfilenames": True,
            "proxy": "",
            "restrictfilenames": False,
            "http_headers": _download_headers(url),
        }
        if _is_bilibili_url(url):
            options.update(
                {
                    "retries": 10,
                    "fragment_retries": 10,
                    "extractor_retries": 5,
                    "http_chunk_size": 1024 * 1024,
                    "continuedl": True,
                    "nopart": False,
                    "concurrent_fragment_downloads": 1,
                    "socket_timeout": 30,
                }
            )
            log_event(
                "Using resumable 1 MB chunks and extended retries for Bilibili",
                category="download",
                job_id=job_id,
            )
        if not selected_format:
            options["format_sort"] = _download_sort(max_height)
        if download_subtitles:
            selected_subtitle_source = requested_subtitle_source if requested_subtitle_source in {"manual", "auto"} else ""
            if selected_subtitle_source:
                subtitle_langs = subtitle_langs[:1] or ["en"]
                log_event(
                    f"Using selected {selected_subtitle_source} site subtitles language={subtitle_langs[0]}",
                    category="download",
                    job_id=job_id,
                )
            else:
                selected_subtitle_source, subtitle_langs = _choose_ytdlp_subtitle_source(url, subtitle_langs, job_id)
            if selected_subtitle_source:
                options.update(
                    {
                        "writesubtitles": selected_subtitle_source == "manual",
                        "writeautomaticsub": selected_subtitle_source == "auto",
                        "subtitleslangs": subtitle_langs,
                        "subtitlesformat": "srt/vtt/best",
                        "convertsubtitles": "srt",
                        "ignoreerrors": True,
                    }
                )
            else:
                download_subtitles = False

        download_started_at = time.time()
        try:
            worker_result = download_in_subprocess(
                url,
                options,
                progress=hook,
                cancel_event=_job_cancel_event(job_id),
                process_callback=lambda process: _register_job_process(job_id, process),
                fault_log_path=LOG_DIR / "crashes" / "yt-dlp-worker-native.log",
            )
        finally:
            _unregister_job_process(job_id)
        _raise_if_cancelled(job_id)
        _log_ytdlp_worker_messages(worker_result, job_id)

        video_path = _downloaded_video_from_info(worker_result) or _newest_video_file_after(output_dir, download_started_at)
        if video_path is None:
            raise RuntimeError("yt-dlp finished but no supported video file was found.")

        title = str(worker_result.get("title") or video_path.name)
        log_event(f"Downloaded video to {video_path}", category="download", job_id=job_id)
        _set_job(job_id, progress=0.94, message="Extracting preview frame")
        session = _prepare_session(video_path, title, "url")
        if download_subtitles:
            subtitle_path = _downloaded_subtitle_file(video_path, output_dir, download_started_at, subtitle_langs)
            if subtitle_path:
                if _attach_downloaded_subtitle(session, subtitle_path, job_id):
                    _cleanup_extra_downloaded_subtitles(video_path, output_dir, download_started_at, subtitle_langs, subtitle_path)
            else:
                log_event("No matching site subtitle file was downloaded", category="download", level=logging.WARNING, job_id=job_id)
        with state_lock:
            session = sessions.get(session.id, session)
        _set_job(
            job_id,
            status="complete",
            progress=1.0,
            message="Video ready",
            result=_session_response(session),
        )
    except (JobCancelled, YtDlpDownloadCancelled):
        log_event("Download cancelled", category="download", job_id=job_id)
        _mark_job_cancelled(job_id)
    except Exception as exc:
        if _cancel_requested(job_id):
            log_event("Download cancelled", category="download", job_id=job_id)
            _mark_job_cancelled(job_id)
            return
        message = str(exc)
        if _is_bilibili_url(url) and "expected" in message.casefold() and "downloaded" in message.casefold():
            message = (
                "Bilibili ended the transfer early. SubtitleYC retried with resumable chunks, "
                "but the CDN did not complete the file. Try the download again or choose a listed AVC format.\n"
                + message
            )
        record_crash(
            "Video download failed",
            exc,
            category="download",
            job_id=job_id,
            extra={
                "url": url,
                "format_selector": format_selector,
                "max_height": max_height,
                "download_subtitles": download_subtitles,
                "tail": message[-2000:],
            },
        )
        log_event(f"Download failed: {message}", category="download", level=logging.ERROR, job_id=job_id)
        _set_job(job_id, status="failed", error=message, message="Download failed")

def _run_ocr_job(job_id: str, session_id: str, request: OCRRequest) -> None:
    try:
        _raise_if_cancelled(job_id)
        session = _get_session(session_id)
        cli_path = find_videocr_cli(prefer_gpu=request.use_gpu)
        if not cli_path:
            if request.use_gpu:
                raise RuntimeError(
                    "VideOCR GPU CLI was not found. Install or bundle the VideOCR GPU build, "
                    "then try GPU acceleration again."
                )
            raise RuntimeError(
                "VideOCR CLI was not found. Install VideOCR or set VIDEOCR_CLI to videocr-cli.exe."
            )

        subtitle_format = _normalize_subtitle_format(request.subtitle_format)
        subtitle_position = request.subtitle_position
        if subtitle_position not in {"center", "left", "right", "any"}:
            subtitle_position = "center"

        settings = VideOCRCliSettings(
            crop_x=request.crop.x,
            crop_y=request.crop.y,
            crop_width=request.crop.width,
            crop_height=request.crop.height,
            language=map_language(request.language),
            frames_to_skip=max(0, request.frame_step - 1),
            conf_threshold=request.min_confidence,
            sim_threshold=round(request.similarity * 100),
            max_merge_gap=request.merge_gap_seconds,
            use_fullframe=request.use_fullframe,
            use_gpu=request.use_gpu,
            use_angle_cls=request.use_angle_cls,
            use_server_model=request.use_server_model,
            brightness_threshold=request.brightness_threshold,
            ssim_threshold=round(request.ssim_threshold * 100),
            subtitle_position=subtitle_position,
            normalize_to_simplified_chinese=request.normalize_chinese,
            post_processing=request.post_processing,
            min_subtitle_duration=request.min_subtitle_duration,
            ocr_image_max_width=request.max_image_width,
            use_dual_zone=request.use_dual_zone,
            start_seconds=request.start_seconds,
            end_seconds=request.end_seconds,
        )

        _set_job(job_id, status="running", progress=0.01, message=f"Starting real VideOCR: {Path(cli_path).name}")
        log_event(
            f"Starting VideOCR source={session.video_path} cli={cli_path} language={settings.language} range={settings.start_seconds}-{settings.end_seconds or 'end'} output={subtitle_format}",
            category="ocr",
            job_id=job_id,
        )
        progress_state = {"bucket": -1}

        def progress(ratio: float, message: str) -> None:
            _raise_if_cancelled(job_id)
            clamped = max(0.01, min(0.98, ratio))
            _set_job(job_id, progress=clamped, message=message)
            bucket = int(clamped * 10)
            if bucket > progress_state["bucket"] and clamped >= 0.1:
                progress_state["bucket"] = bucket
                log_event(f"VideOCR {int(clamped * 100)}%: {message}", category="ocr", job_id=job_id)

        source_srt_path = _subtitle_storage_path(session, "srt")
        cancel_event = _job_cancel_event(job_id)
        try:
            srt_text = run_videocr_cli(
                Path(session.video_path),
                source_srt_path,
                settings,
                VIDEOCR_RUNTIME_DIR,
                progress=progress,
                cli_path=cli_path,
                cancel_event=cancel_event,
                process_callback=lambda process: _register_job_process(job_id, process),
            )
        finally:
            _unregister_job_process(job_id)
        _raise_if_cancelled(job_id)
        srt_text = _normalize_generated_srt_timing(
            srt_text,
            session,
            request.timing_offset_seconds,
            request.snap_to_frame,
        )
        source_srt_path.write_text(srt_text, encoding="utf-8")
        subtitle_path, cue_count = _write_subtitle_output(
            session.id,
            srt_text,
            source_srt_path,
            subtitle_format,
            session.original_name,
        )
        log_event(
            f"VideOCR created {cue_count} cues as {_subtitle_label(subtitle_format)} at {subtitle_path}",
            category="ocr",
            job_id=job_id,
        )

        with state_lock:
            stored = sessions[session.id]
            stored.srt_path = str(subtitle_path)
            stored.subtitle_format = subtitle_format

        _set_job(
            job_id,
            status="complete",
            progress=1.0,
            message=f"Created {cue_count} subtitle cues as {_subtitle_label(subtitle_format)} with real VideOCR",
            result={
                "cue_count": cue_count,
                "subtitle_url": f"/api/videos/{session.id}/subtitle",
                "subtitle_format": subtitle_format,
                "subtitle_filename": _subtitle_filename(stored),
                "srt_url": f"/api/videos/{session.id}/subtitle",
                "session": _session_response(stored),
            },
        )
    except (JobCancelled, VideOCRCancelled):
        log_event("VideOCR cancelled", category="ocr", job_id=job_id)
        _mark_job_cancelled(job_id)
    except Exception as exc:
        if _cancel_requested(job_id):
            log_event("VideOCR cancelled", category="ocr", job_id=job_id)
            _mark_job_cancelled(job_id)
            return
        log_event(f"VideOCR failed: {exc}", category="ocr", level=logging.ERROR, job_id=job_id)
        _set_job(job_id, status="failed", error=str(exc), message="VideOCR failed")

def _authenticated_page(request: Request, filename: str, app_token: str | None = None) -> Response:
    if app_token:
        if not secrets.compare_digest(app_token, API_TOKEN):
            return JSONResponse({"detail": "Invalid application launch token."}, status_code=403)
        clean_url = request.url.remove_query_params("app_token")
        response = RedirectResponse(str(clean_url), status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            API_TOKEN,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response
    if not _request_has_valid_token(request):
        return JSONResponse({"detail": "Open SubtitleYC from its desktop launcher."}, status_code=401)
    return FileResponse(STATIC_DIR / filename)


@app.get("/")
def index(request: Request, app_token: str | None = Query(default=None)) -> Response:
    return _authenticated_page(request, "index.html", app_token)


@app.get("/editor")
def editor(request: Request, app_token: str | None = Query(default=None)) -> Response:
    return _authenticated_page(request, "editor.html", app_token)
@app.post("/api/videos/url/formats")
def list_url_formats(request: FormatProbeRequest) -> dict[str, Any]:
    try:
        payload = _probe_ytdlp_formats(request.url)
    except RuntimeError as exc:
        log_event(str(exc), category="download", level=logging.WARNING)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    host = urllib.parse.urlparse(request.url).hostname or "unknown"
    log_event(f"Format probe host={host} formats={payload['format_count']}", category="download")
    return payload

@app.post("/api/videos/url/subtitles")
def list_url_subtitles(request: SubtitleProbeRequest) -> dict[str, Any]:
    try:
        payload = _probe_ytdlp_subtitles(request.url)
    except RuntimeError as exc:
        log_event(str(exc), category="download", level=logging.WARNING)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    host = urllib.parse.urlparse(request.url).hostname or "unknown"
    log_event(f"Subtitle probe host={host} tracks={payload['track_count']}", category="download")
    return payload

@app.post("/api/videos/url/subtitle")
def download_url_subtitle(request: SubtitleDownloadRequest) -> dict[str, Any]:
    job = _create_job("subtitle_download")
    _submit_job(
        job,
        _download_site_subtitle,
        job.id,
        request.url,
        request.download_dir,
        request.output_path,
        request.subtitle_language,
        request.subtitle_source,
    )
    return {"job_id": job.id}

@app.post("/api/videos/url")
def create_video_from_url(request: URLRequest) -> dict[str, Any]:
    job = _create_job("download")
    _submit_job(
        job,
        _download_with_ytdlp,
        job.id,
        request.url,
        request.max_height,
        request.format_selector,
        request.download_dir,
        request.download_subtitles,
        request.subtitle_languages,
        request.subtitle_source,
    )
    return {"job_id": job.id}


@app.post("/api/videos/open")
def open_local_video(request: LocalVideoOpenRequest) -> dict[str, Any]:
    source = _resolve_external_video_path(request.path)
    session_path = source
    source_type = "local"
    copied = False
    if request.keep_copy:
        session_path = _copy_video_to_uploads(source)
        source_type = "upload"
        copied = True
        log_event(f"Copied opened video to {session_path}", category="upload")
    else:
        log_event(f"Opened local video without copying {source}", category="upload")
    try:
        session = _prepare_session(session_path, source.name, source_type)
        if not copied:
            _remember_local_video(source)
    except VideoToolError as exc:
        log_event(f"Open video probe failed: {exc}", category="upload", level=logging.ERROR)
        if copied:
            session_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _session_response(session)

@app.post("/api/videos/upload")
async def upload_video(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose a supported video file.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            request_bytes = int(content_length)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid upload size.") from None
        if request_bytes > MAX_VIDEO_UPLOAD_BYTES + 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Video uploads are limited to {MAX_VIDEO_UPLOAD_MB} MB.")

    stem = _clean_filename_stem(Path(file.filename or "uploaded video").stem, "uploaded video")
    target = _unique_file_path(UPLOAD_DIR, stem, suffix)
    written = 0
    try:
        _ensure_free_disk(UPLOAD_DIR)
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_VIDEO_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"Video uploads are limited to {MAX_VIDEO_UPLOAD_MB} MB.")
                _ensure_free_disk(UPLOAD_DIR)
                output.write(chunk)
        log_event(f"Imported video copy to {target}", category="upload")
        session = _prepare_session(target, file.filename or target.name, "upload")
        return _session_response(session)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except (OSError, RuntimeError, VideoToolError) as exc:
        target.unlink(missing_ok=True)
        log_event(f"Upload failed: {exc}", category="upload", level=logging.ERROR)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@app.get("/api/library")
def list_library() -> dict[str, Any]:
    return _library_response()


@app.post("/api/library/videos/open")
def open_library_video(request: LibraryFileRequest) -> dict[str, Any]:
    category = request.category.strip().casefold()
    if category == "local":
        path = _resolve_external_video_path(request.relative_path)
        source_type = "local"
        failure_label = "Original video probe failed"
    else:
        path = _resolve_library_file(request, {"uploads": UPLOAD_DIR, "downloads": DOWNLOAD_DIR}, VIDEO_EXTENSIONS)
        source_type = f"library-{category}"
        failure_label = "Stored video probe failed"
    try:
        session = _prepare_session(path, path.name, source_type)
    except VideoToolError as exc:
        log_event(f"{failure_label}: {exc}", category="library", level=logging.ERROR)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if category == "local":
        _remember_local_video(path)
    log_event(f"Opened video from Previous Projects {path}", category="library")
    return _session_response(session)

@app.post("/api/library/subtitles/import")
def import_library_subtitle(request: LibrarySubtitleImportRequest) -> dict[str, Any]:
    path = _resolve_library_file(request, {"results": RESULTS_DIR, "downloads": DOWNLOAD_DIR}, DOWNLOADED_SUBTITLE_EXTENSIONS)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    payload = _import_subtitle_cues(request.session_id, path.name, text)
    log_event(f"Loaded stored subtitle {path}", category="library")
    return payload

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with state_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)



@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    process: subprocess.Popen[Any] | None = None
    with state_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status in {"complete", "failed", "cancelled"}:
            return _job_response(job)
        event = job_cancel_events.get(job_id)
        if event is None:
            event = threading.Event()
            job_cancel_events[job_id] = event
        event.set()
        process = job_processes.get(job_id)
        if job.status == "queued":
            job.status = "cancelled"
            job.message = "Cancelled"
            job.progress = 0.0
        else:
            job.message = "Cancelling..."
        response = _job_response(job)

    _stop_registered_process(process)
    log_event(f"Cancel requested for {job.kind} job", category=job.kind, job_id=job.id)
    return response


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return _settings_response()


@app.put("/api/settings")
def save_settings(settings: AppSettings) -> dict[str, Any]:
    return _settings_response(_save_settings(settings))


@app.get("/api/storage")
def get_storage() -> dict[str, Any]:
    return _storage_response()


@app.post("/api/storage/clear")
def clear_storage(request: StorageClearRequest) -> dict[str, Any]:
    return _clear_storage_categories(request.categories)


@app.post("/api/crashes/frontend")
def record_frontend_crash(request: FrontendCrashRequest) -> dict[str, Any]:
    path = record_crash(
        "Frontend crash",
        traceback_text=request.stack or request.message or "No frontend stack was supplied.",
        extra={
            "message": request.message,
            "source": request.source,
            "url": request.url,
            "user_agent": request.user_agent,
        },
    )
    return {"ok": True, "path": str(path) if path else None}

@app.get("/api/logs")
def list_logs(
    category: str = Query(default="all", max_length=24),
    level: str = Query(default="all", max_length=12),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict[str, Any]:
    return {
        "logs": get_log_entries(category=category, level=level, limit=limit),
        "log_dir": str(LOG_DIR),
        "crash_dir": str(LOG_DIR / "crashes"),
    }


@app.delete("/api/logs")
def clear_logs() -> dict[str, Any]:
    clear_log_entries()
    log_event("Log view cleared", category="app")
    return {"cleared": True}


@app.get("/api/videos/{session_id}")
def get_video(session_id: str) -> dict[str, Any]:
    return _session_response(_get_session(session_id))



def _session_duration(session: VideoSession) -> float:
    try:
        return max(0.0, float((session.metadata or {}).get("duration") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _session_fps(session: VideoSession) -> float:
    try:
        return max(0.0, float((session.metadata or {}).get("fps") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _frame_time_for_session(session: VideoSession, time_seconds: float) -> tuple[int, float]:
    duration = _session_duration(session)
    requested = max(0.0, min(float(time_seconds or 0.0), duration if duration > 0 else float(time_seconds or 0.0)))
    fps = _session_fps(session)
    if fps <= 0:
        return int(round(requested * 1000)), requested

    frame_count = int((session.metadata or {}).get("frame_count") or 0)
    if frame_count <= 0 and duration > 0:
        frame_count = int(math.ceil(duration * fps))
    frame_index = max(0, int(round(requested * fps)))
    if frame_count > 0:
        frame_index = min(frame_index, max(0, frame_count - 1))
    return frame_index, frame_index / fps


def _prune_frame_cache(frame_dir: Path, keep_limit: int = FRAME_CACHE_LIMIT) -> None:
    try:
        frames = sorted(
            (path for path in frame_dir.glob("*.jpg") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for path in frames[keep_limit:]:
        try:
            path.unlink()
        except OSError:
            pass


@app.get("/api/videos/{session_id}/preview")
def get_preview(session_id: str) -> Response:
    session = _get_session(session_id)
    decoder = _get_frame_decoder(session)
    duration = float((session.metadata or {}).get("duration") or 0)
    target_frame = decoder.frame_index_for_time(duration * 0.25 if duration > 0 else 0)
    try:
        frame_bytes = decoder.get_frame_bytes(target_frame)
    except VideoToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(content=frame_bytes, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

@app.get("/api/videos/{session_id}/frame")
def get_video_frame(
    session_id: str,
    time_seconds: float = Query(default=0.0, ge=0.0),
    frame_index: int | None = Query(default=None, ge=0),
) -> Response:
    session = _get_session(session_id)
    decoder = _get_frame_decoder(session)
    target_frame = decoder.frame_index_for_time(time_seconds) if frame_index is None else frame_index
    try:
        frame_bytes = decoder.get_frame_bytes(target_frame)
    except VideoToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-SubtitleYC-Frame-Index": str(decoder.frame_index_for_time(time_seconds) if frame_index is None else target_frame),
        },
    )


@app.get("/api/videos/{session_id}/media")
def get_video_media(session_id: str) -> FileResponse:
    session = _get_session(session_id)
    path = Path(session.video_path)
    return FileResponse(path, media_type=_video_media_type(path), filename=path.name)



@app.post("/api/videos/{session_id}/preview-cache")
def create_preview_cache_job(session_id: str) -> dict[str, Any]:
    _get_session(session_id)
    job = _create_job("preview")
    _submit_job(job, _run_preview_cache_job, job.id, session_id)
    return {"job_id": job.id}


@app.post("/api/videos/{session_id}/preview")
def refresh_preview(session_id: str, time_seconds: float = 0.0) -> dict[str, Any]:
    session = _get_session(session_id)
    decoder = _get_frame_decoder(session)
    try:
        decoder.get_frame_bytes(decoder.frame_index_for_time(time_seconds))
    except VideoToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _session_response(session)

@app.post("/api/videos/{session_id}/ocr")
def create_ocr_job(session_id: str, request: OCRRequest) -> dict[str, Any]:
    _get_session(session_id)
    if request.use_gpu and not find_videocr_cli(prefer_gpu=True):
        raise HTTPException(
            status_code=409,
            detail="GPU acceleration is unavailable because the VideOCR GPU build is not installed.",
        )
    job = _create_job("ocr")
    _submit_job(job, _run_ocr_job, job.id, session_id, request)
    return {"job_id": job.id}


def _subtitle_file_response(session_id: str) -> FileResponse:
    session = _get_session(session_id)
    if not session.srt_path:
        raise HTTPException(status_code=404, detail="Subtitle file has not been created yet")
    subtitle_path = Path(session.srt_path)
    if not subtitle_path.is_file():
        raise HTTPException(status_code=404, detail="Subtitle file was not found")
    return FileResponse(
        subtitle_path,
        media_type=_subtitle_media_type(session.subtitle_format),
        filename=_subtitle_filename(session),
    )



def _subtitle_srt_file_response(session_id: str) -> FileResponse:
    session = _get_session(session_id)
    subtitle_path = _subtitle_source_path(session)
    if subtitle_path is None or not subtitle_path.is_file():
        raise HTTPException(status_code=404, detail="SRT subtitle file was not found")
    return FileResponse(
        subtitle_path,
        media_type="application/x-subrip",
        filename=_subtitle_download_filename(session, "srt"),
    )


@app.get("/api/videos/{session_id}/subtitle.srt")
def download_subtitle_srt(session_id: str) -> FileResponse:
    return _subtitle_srt_file_response(session_id)

@app.get("/api/videos/{session_id}/subtitle")
@app.get("/api/videos/{session_id}/srt")
def download_subtitle(session_id: str) -> FileResponse:
    return _subtitle_file_response(session_id)


@app.get("/api/videos/{session_id}/subtitles")
def get_subtitle_cues(session_id: str) -> dict[str, Any]:
    return _subtitle_cues_response(_get_session(session_id))



@app.post("/api/videos/{session_id}/subtitles/import")
async def import_subtitle_cues(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Choose a subtitle file to load.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Subtitle file is too large to load.")
    text = content.decode("utf-8-sig", errors="replace")
    return _import_subtitle_cues(session_id, file.filename, text)

@app.put("/api/videos/{session_id}/subtitles")
def save_subtitle_cues(session_id: str, request: SubtitleEditRequest) -> dict[str, Any]:
    return _save_subtitle_cues(session_id, request)




def _yt_dlp_version() -> str | None:
    try:
        import yt_dlp.version as yt_dlp_version
    except Exception:  # noqa: BLE001 - tool availability should not break system status.
        return None
    return str(getattr(yt_dlp_version, "__version__", "") or "") or None


def _videocr_cli_version(cli_path: str | None) -> str | None:
    if not cli_path:
        return None
    path = Path(str(cli_path))
    for value in [path.name, *reversed(path.parts), str(cli_path)]:
        match = re.search(r"v?\d+(?:\.\d+)+", value, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


@app.get("/api/system")
def system_status() -> dict[str, Any]:
    videocr_cli = find_videocr_cli()
    videocr_gpu_cli = find_videocr_cli(prefer_gpu=True)
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    tools_dir = RUNTIME_ROOT / "tools"
    videocr_build = _bundled_videocr_metadata()
    payload = {
        "app_version": __version__,
        "release_label": __release__,
        "ffmpeg": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path,
        "ffprobe": ffprobe_path is not None,
        "ffprobe_path": ffprobe_path,
        "videocr_cli": videocr_cli is not None,
        "videocr_cli_path": videocr_cli,
        "videocr_gpu_cli": videocr_gpu_cli is not None,
        "videocr_gpu_cli_path": videocr_gpu_cli,
        "bundled_tools_dir": str(tools_dir),
        "videocr_build_variant": videocr_build.get("variant"),
        "max_jobs": MAX_WORKERS,
        "yt_dlp_fragment_downloads": YTDLP_FRAGMENT_DOWNLOADS,
        "videocr_cli_version": _videocr_cli_version(videocr_cli),
        "videocr_gpu_cli_version": _videocr_cli_version(videocr_gpu_cli),
        "yt_dlp_version": _yt_dlp_version(),
    }
    return payload

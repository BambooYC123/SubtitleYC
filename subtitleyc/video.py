from __future__ import annotations

import io
import json
import math
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .process import popen_hidden_subprocess, run_hidden_subprocess


VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


class VideoToolError(RuntimeError):
    """Raised when a required native video tool fails."""


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise VideoToolError(f"Required command not found: {name}")


def parse_fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            den = float(denominator)
            return float(numerator) / den if den else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def probe_video(video_path: Path) -> dict[str, Any]:
    require_binary("ffprobe")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = run_hidden_subprocess(command, capture_output=True, text=True, check=False)
    stderr = result.stderr or ""
    stdout = result.stdout or ""
    if result.returncode != 0:
        raise VideoToolError(stderr.strip() or "ffprobe failed")
    if not stdout.strip():
        raise VideoToolError("ffprobe returned no video information")

    try:
        data = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise VideoToolError("ffprobe returned invalid video information") from exc
    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not video_stream:
        raise VideoToolError("No video stream found")

    duration = float(video_stream.get("duration") or data.get("format", {}).get("duration") or 0)
    fps = parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    frame_count = int(video_stream.get("nb_frames") or 0)
    if not frame_count and duration > 0 and fps > 0:
        frame_count = int(math.ceil(duration * fps))

    return {
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": fps,
        "duration": duration,
        "frame_count": frame_count,
        "codec": video_stream.get("codec_name") or "unknown",
    }


def extract_preview_frame(
    video_path: Path,
    output_path: Path,
    duration: float = 0.0,
    seek_seconds: float | None = None,
) -> None:
    require_binary("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if seek_seconds is None:
        seek_seconds = 0.1
        if duration > 1:
            seek_seconds = min(10.0, max(0.1, duration * 0.25))
    else:
        seek_seconds = max(0.0, seek_seconds)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{seek_seconds:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]
    result = run_hidden_subprocess(command, capture_output=True, text=True, check=False)
    if result.returncode == 0 and output_path.exists():
        return

    fallback = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]
    fallback_result = run_hidden_subprocess(fallback, capture_output=True, text=True, check=False)
    if fallback_result.returncode != 0 or not output_path.exists():
        message = fallback_result.stderr.strip() or result.stderr.strip() or "ffmpeg failed"
        raise VideoToolError(message)


class StreamingFrameDecoder:
    """Session decoder that mirrors VideOCR's PyAV-first preview path.

    The decoder keeps a PyAV container open, seeks by stream timestamp, decodes
    nearby frames forward, and caches display-sized JPEGs by frame index. A
    hidden ffmpeg pipe remains as a fallback for codecs PyAV cannot handle.
    """

    def __init__(
        self,
        video_path: Path,
        metadata: dict[str, Any],
        cache_dir: Path,
        cache_limit: int = 300,
        restart_gap_frames: int = 45,
        max_preview_width: int = 720,
    ) -> None:
        self.video_path = Path(video_path)
        self.metadata = dict(metadata or {})
        self.cache_dir = Path(cache_dir)
        self.cache_limit = max(1, int(cache_limit))
        self.restart_gap_frames = max(1, int(restart_gap_frames))
        self.max_preview_width = max(320, int(max_preview_width))
        self.fps = float(self.metadata.get("fps") or 0.0)
        self.duration = float(self.metadata.get("duration") or 0.0)
        self.frame_count = int(self.metadata.get("frame_count") or 0)
        if self.frame_count <= 0 and self.duration > 0 and self.fps > 0:
            self.frame_count = int(math.ceil(self.duration * self.fps))
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._buffer = bytearray()
        self._next_frame_index = 0
        self._av_container: Any | None = None
        self._av_stream: Any | None = None
        self._av_frames: Any | None = None
        self._av_next_frame_index = 0
        self._pyav_failed = False
        self._frame_bytes: OrderedDict[int, bytes] = OrderedDict()
        self.last_used = time.monotonic()

    def close(self) -> None:
        with self._lock:
            self._close_av()
            self._stop_process()

    def frame_index_for_time(self, time_seconds: float) -> int:
        requested = max(0.0, float(time_seconds or 0.0))
        if self.duration > 0:
            requested = min(requested, self.duration)
        if self.fps <= 0:
            return int(round(requested * 1000))
        frame_index = max(0, int(round(requested * self.fps)))
        return self._clamp_frame_index(frame_index)

    def frame_time(self, frame_index: int) -> float:
        if self.fps <= 0:
            return 0.0
        return self._clamp_frame_index(frame_index) / self.fps

    def get_frame(self, frame_index: int) -> Path:
        with self._lock:
            self.last_used = time.monotonic()
            target = self._clamp_frame_index(frame_index)
            cached = self._cache_path(target)
            if cached.is_file():
                cached.touch(exist_ok=True)
                return cached
            data = self.get_frame_bytes(target)
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
            return cached

    def get_frame_bytes(self, frame_index: int) -> bytes:
        with self._lock:
            self.last_used = time.monotonic()
            target = self._clamp_frame_index(frame_index)
            cached_bytes = self._cached_frame_bytes(target)
            if cached_bytes is not None:
                return cached_bytes

            cached_path = self._cache_path(target)
            if cached_path.is_file():
                cached_path.touch(exist_ok=True)
                data = cached_path.read_bytes()
                self._remember_frame_bytes(target, data)
                return data

            if not self._pyav_failed:
                try:
                    pyav_frame = self._get_frame_bytes_with_pyav(target)
                    if pyav_frame is not None:
                        return pyav_frame
                except ImportError:
                    self._pyav_failed = True
                    self._close_av()
                except Exception:
                    self._pyav_failed = True
                    self._close_av()

            frame_path = self._get_frame_with_ffmpeg(target)
            data = frame_path.read_bytes()
            self._remember_frame_bytes(target, data)
            return data

    def _clamp_frame_index(self, frame_index: int) -> int:
        value = max(0, int(frame_index or 0))
        if self.frame_count > 0:
            value = min(value, max(0, self.frame_count - 1))
        return value

    def _cache_path(self, frame_index: int) -> Path:
        return self.cache_dir / f"{frame_index:010d}.jpg"

    def _cached_frame_bytes(self, frame_index: int) -> bytes | None:
        key = self._clamp_frame_index(frame_index)
        data = self._frame_bytes.get(key)
        if data is None:
            return None
        self._frame_bytes.move_to_end(key)
        return data

    def _remember_frame_bytes(self, frame_index: int, data: bytes) -> None:
        key = self._clamp_frame_index(frame_index)
        self._frame_bytes[key] = data
        self._frame_bytes.move_to_end(key)
        while len(self._frame_bytes) > self.cache_limit:
            self._frame_bytes.popitem(last=False)

    def _get_frame_bytes_with_pyav(self, target: int) -> bytes | None:
        if self.fps <= 0:
            return None
        if self._av_should_restart(target):
            self._start_av(target)
        if self._av_container is None or self._av_stream is None or self._av_frames is None:
            return None

        stale_limit = self._clamp_frame_index(target + self.restart_gap_frames)
        for frame in self._av_frames:
            current = self._frame_index_from_av_frame(frame)
            if current < 0:
                current = self._av_next_frame_index
            current = self._clamp_frame_index(current)
            if current > stale_limit:
                break
            data = self._cached_frame_bytes(current)
            if data is None:
                data = self._encode_av_frame(frame)
                self._remember_frame_bytes(current, data)
            self._av_next_frame_index = max(self._av_next_frame_index, current + 1)
            if current == target:
                self._prune_cache()
                return data
            if current > target:
                break
        return None

    def _av_should_restart(self, target: int) -> bool:
        if self._av_container is None or self._av_stream is None or self._av_frames is None:
            return True
        if target < self._av_next_frame_index:
            return True
        return target - self._av_next_frame_index > self.restart_gap_frames

    def _start_av(self, frame_index: int) -> None:
        import av

        self._close_av()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        container = av.open(str(self.video_path))
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if frame_index > 0:
            seek_time = self.frame_time(frame_index)
            time_base = float(stream.time_base or 0)
            if time_base > 0:
                container.seek(int(seek_time / time_base), stream=stream, backward=True)
            else:
                container.seek(int(seek_time * 1_000_000), backward=True)
        self._av_container = container
        self._av_stream = stream
        self._av_frames = container.decode(stream)
        self._av_next_frame_index = 0

    def _close_av(self) -> None:
        container = self._av_container
        self._av_container = None
        self._av_stream = None
        self._av_frames = None
        self._av_next_frame_index = 0
        if container is None:
            return
        try:
            container.close()
        except Exception:
            pass

    def _frame_index_from_av_frame(self, frame: Any) -> int:
        frame_time = getattr(frame, "time", None)
        if frame_time is None and getattr(frame, "pts", None) is not None:
            time_base = getattr(frame, "time_base", None)
            if time_base is not None:
                frame_time = float(frame.pts * time_base)
        if frame_time is None:
            return -1
        return self.frame_index_for_time(float(frame_time))

    def _preview_dimensions(self, width: int, height: int) -> tuple[int, int]:
        width = max(1, int(width or 1))
        height = max(1, int(height or 1))
        if width <= self.max_preview_width:
            return width, height
        scale = self.max_preview_width / width
        return self.max_preview_width, max(1, int(round(height * scale)))

    def _encode_av_frame(self, frame: Any) -> bytes:
        width, height = self._preview_dimensions(frame.width, frame.height)
        resized = frame.reformat(width=width, height=height, format="rgb24")
        image = resized.to_image()
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=False)
        return output.getvalue()

    def _get_frame_with_ffmpeg(self, target: int) -> Path:
        cached = self._cache_path(target)
        if self._should_restart(target):
            self._start_process(target)

        while self._next_frame_index <= target:
            frame = self._read_next_jpeg()
            if not frame:
                self._stop_process()
                extract_preview_frame(self.video_path, cached, seek_seconds=self.frame_time(target))
                return cached

            current = self._next_frame_index
            path = self._cache_path(current)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(frame)
            self._remember_frame_bytes(current, frame)
            self._next_frame_index += 1
            if current == target:
                self._prune_cache()
                return path

        if cached.is_file():
            return cached
        raise VideoToolError("Could not decode preview frame")

    def _should_restart(self, target: int) -> bool:
        if self._process is None or self._process.poll() is not None:
            return True
        if target < self._next_frame_index:
            return True
        return target - self._next_frame_index > self.restart_gap_frames

    def _start_process(self, frame_index: int) -> None:
        require_binary("ffmpeg")
        self._stop_process()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        start_time = self.frame_time(frame_index)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start_time:.6f}",
            "-i",
            str(self.video_path),
            "-an",
            "-sn",
            "-map",
            "0:v:0",
            "-vf",
            f"scale=w='min({self.max_preview_width},iw)':h=-2",
            "-q:v",
            "3",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        self._process = popen_hidden_subprocess(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._buffer = bytearray()
        self._next_frame_index = self._clamp_frame_index(frame_index)

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        self._buffer = bytearray()
        if process is None:
            return
        try:
            if process.stdout:
                process.stdout.close()
        except OSError:
            pass
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    def _read_next_jpeg(self) -> bytes:
        process = self._process
        if process is None or process.stdout is None:
            return b""

        while True:
            start = self._buffer.find(JPEG_SOI)
            if start >= 0:
                end = self._buffer.find(JPEG_EOI, start + len(JPEG_SOI))
                if end >= 0:
                    frame_end = end + len(JPEG_EOI)
                    frame = bytes(self._buffer[start:frame_end])
                    del self._buffer[:frame_end]
                    return frame
                if start > 0:
                    del self._buffer[:start]
            elif len(self._buffer) > 1:
                del self._buffer[:-1]

            chunk = process.stdout.read(65536)
            if not chunk:
                return b""
            self._buffer.extend(chunk)

    def _prune_cache(self) -> None:
        try:
            frames = sorted(
                (path for path in self.cache_dir.glob("*.jpg") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in frames[self.cache_limit :]:
            try:
                path.unlink()
            except OSError:
                pass
def newest_video_file(directory: Path) -> Path | None:
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import av
from PIL import Image


class NativeVideoDecoder:
    def __init__(
        self,
        video_path: str,
        metadata: dict[str, Any],
        *,
        preview_cache_dir: Path | None = None,
        cache_limit: int = 240,
    ) -> None:
        self.video_path = str(video_path)
        self.metadata = dict(metadata or {})
        self.preview_cache_dir = Path(preview_cache_dir) if preview_cache_dir else None
        self.cache_limit = max(30, int(cache_limit or 240))
        self.container: Any | None = None
        self.stream: Any | None = None
        self.frames: Any | None = None
        self.last_pts: int | None = None
        self.last_frame_index: int | None = None
        self.cache_dimensions: tuple[int, int] | None = None
        self.frame_cache: OrderedDict[int, Image.Image] = OrderedDict()
        self.cache_lock = threading.RLock()
        self.frame_count = int(self.metadata.get("frame_count") or 0)
        self.fps = float(self.metadata.get("fps") or 0) or 24.0
        self.duration = float(self.metadata.get("duration") or 0)
        if self.frame_count <= 0 and self.duration > 0 and self.fps > 0:
            self.frame_count = int(round(self.duration * self.fps))
        self.open()

    def open(self) -> None:
        self.close()
        self.container = av.open(self.video_path)
        self.stream = self.container.streams.video[0]
        self.stream.thread_type = "FRAME"
        self.frames = self.container.decode(self.stream)
        self.last_pts = None
        self.last_frame_index = None

    def close(self) -> None:
        container = self.container
        self.container = None
        self.stream = None
        self.frames = None
        self.last_pts = None
        self.last_frame_index = None
        if container is not None:
            try:
                container.close()
            except Exception:
                pass

    def frame_time(self, frame_index: int) -> float:
        if self.fps <= 0:
            return 0.0
        return self.clamp_frame(frame_index) / self.fps

    def clamp_frame(self, frame_index: int) -> int:
        value = max(0, int(round(frame_index)))
        if self.frame_count > 0:
            value = min(value, self.frame_count - 1)
        return value

    def frame_index_for_time(self, seconds: float) -> int:
        value = max(0.0, float(seconds or 0.0))
        if self.duration > 0:
            value = min(value, self.duration)
        return self.clamp_frame(round(value * self.fps))

    def _target_pts_for_stream(self, stream: Any | None, frame_index: int) -> int:
        if stream is None:
            return 0
        time_base = float(stream.time_base or 0)
        seconds = self.frame_time(frame_index)
        if time_base > 0:
            return int(seconds / time_base)
        return int(seconds * 1_000_000)

    def _target_pts(self, frame_index: int) -> int:
        return self._target_pts_for_stream(self.stream, frame_index)

    def _frame_index_from_frame(self, frame: Any, fallback: int) -> int:
        frame_time = getattr(frame, "time", None)
        if frame_time is None and getattr(frame, "pts", None) is not None:
            time_base = getattr(frame, "time_base", None)
            if time_base is not None:
                frame_time = float(frame.pts * time_base)
        if frame_time is None:
            return self.clamp_frame(fallback)
        return self.frame_index_for_time(float(frame_time))

    def _seek(self, frame_index: int) -> None:
        if self.container is None or self.stream is None:
            self.open()
            return
        target_pts = self._target_pts(frame_index)
        try:
            self.container.seek(target_pts, stream=self.stream, backward=True)
        except Exception:
            self.open()
            if self.container is not None and self.stream is not None:
                self.container.seek(target_pts, stream=self.stream, backward=True)
        self.frames = self.container.decode(self.stream)
        self.last_pts = None
        self.last_frame_index = None

    def _needs_seek(self, target: int) -> bool:
        if self.container is None or self.stream is None or self.frames is None:
            return True
        if self.last_frame_index is None:
            return target != 0
        if target < self.last_frame_index:
            return True
        return target - self.last_frame_index > max(2, int(self.fps * 1.5))

    def _display_dimensions(self, display_size: tuple[int, int]) -> tuple[int, int]:
        source_w = int(self.metadata.get("width") or 1)
        source_h = int(self.metadata.get("height") or 1)
        max_w = max(1, int(display_size[0] or source_w))
        max_h = max(1, int(display_size[1] or source_h))
        scale = min(max_w / source_w, max_h / source_h)
        width = max(2, int(source_w * scale))
        height = max(2, int(source_h * scale))
        return width, height

    def _prepare_cache_dimensions(self, dimensions: tuple[int, int]) -> None:
        with self.cache_lock:
            if self.cache_dimensions == dimensions:
                return
            self.cache_dimensions = dimensions
            self.frame_cache.clear()

    def _cached_image(self, frame_index: int, dimensions: tuple[int, int]) -> Image.Image | None:
        key = self.clamp_frame(frame_index)
        with self.cache_lock:
            if self.cache_dimensions != dimensions:
                return None
            image = self.frame_cache.get(key)
            if image is None:
                return None
            self.frame_cache.move_to_end(key)
            return image

    def _prune_memory_cache(self) -> None:
        while len(self.frame_cache) > self.cache_limit:
            self.frame_cache.popitem(last=False)

    def set_cache_limit(self, cache_limit: int) -> None:
        next_limit = max(30, int(cache_limit or self.cache_limit))
        with self.cache_lock:
            self.cache_limit = next_limit
            self._prune_memory_cache()

    def _remember_image(self, frame_index: int, dimensions: tuple[int, int], image: Image.Image) -> None:
        key = self.clamp_frame(frame_index)
        with self.cache_lock:
            if self.cache_dimensions != dimensions:
                self.cache_dimensions = dimensions
                self.frame_cache.clear()
            self.frame_cache[key] = image
            self.frame_cache.move_to_end(key)
            self._prune_memory_cache()

    def _cache_path(self, frame_index: int) -> Path | None:
        if self.preview_cache_dir is None:
            return None
        return self.preview_cache_dir / f"{self.clamp_frame(frame_index):010d}.jpg"

    def _load_disk_cached_image(self, frame_index: int, dimensions: tuple[int, int]) -> Image.Image | None:
        cache_path = self._cache_path(frame_index)
        if cache_path is None or not cache_path.is_file():
            return None
        try:
            with Image.open(cache_path) as image:
                frame = image.convert("RGB")
                if frame.size != dimensions:
                    frame = frame.resize(dimensions, Image.Resampling.BILINEAR)
                else:
                    frame = frame.copy()
        except OSError:
            return None
        self._remember_image(frame_index, dimensions, frame)
        return frame

    def _image_from_frame(self, frame: Any, dimensions: tuple[int, int]) -> Image.Image:
        resized = frame.reformat(width=dimensions[0], height=dimensions[1], format="rgb24")
        return resized.to_image()

    def get_frame(self, frame_index: int, display_size: tuple[int, int]) -> tuple[Image.Image, int]:
        target = self.clamp_frame(frame_index)
        dimensions = self._display_dimensions(display_size)
        self._prepare_cache_dimensions(dimensions)
        cached = self._cached_image(target, dimensions)
        if cached is not None:
            return cached, target
        disk_cached = self._load_disk_cached_image(target, dimensions)
        if disk_cached is not None:
            return disk_cached, target

        if self._needs_seek(target):
            self._seek(target)
        if self.frames is None:
            self.open()

        best_frame = None
        best_index = target
        fallback_index = self.last_frame_index or 0
        for frame in self.frames:
            index = self._frame_index_from_frame(frame, fallback_index)
            fallback_index = index + 1
            self.last_frame_index = index
            self.last_pts = getattr(frame, "pts", None)
            best_frame = frame
            best_index = index
            if index >= target:
                break
        if best_frame is None:
            self._seek(target)
            for frame in self.frames:
                best_frame = frame
                best_index = self._frame_index_from_frame(frame, target)
                self.last_frame_index = best_index
                break
        if best_frame is None:
            raise RuntimeError("Could not decode preview frame")

        image = self._image_from_frame(best_frame, dimensions)
        best_index = self.clamp_frame(best_index)
        self._remember_image(best_index, dimensions, image)
        return image, best_index

    def warm_frames(
        self,
        start_index: int,
        end_index: int,
        display_size: tuple[int, int],
        stop_event: threading.Event,
    ) -> int:
        if stop_event.is_set():
            return 0
        start = self.clamp_frame(start_index)
        end = self.clamp_frame(end_index)
        if end < start:
            start, end = end, start
        dimensions = self._display_dimensions(display_size)
        self._prepare_cache_dimensions(dimensions)
        warmed = 0

        for frame_index in range(start, end + 1):
            if stop_event.is_set():
                return warmed
            if self._cached_image(frame_index, dimensions) is not None:
                continue
            if self._load_disk_cached_image(frame_index, dimensions) is not None:
                warmed += 1

        missing = [
            frame_index
            for frame_index in range(start, end + 1)
            if self._cached_image(frame_index, dimensions) is None
        ]
        if not missing or stop_event.is_set():
            return warmed

        container = None
        try:
            container = av.open(self.video_path)
            stream = container.streams.video[0]
            stream.thread_type = "FRAME"
            if start > 0:
                container.seek(self._target_pts_for_stream(stream, start), stream=stream, backward=True)
            for frame in container.decode(stream):
                if stop_event.is_set():
                    break
                index = self._frame_index_from_frame(frame, start)
                if index < start:
                    continue
                if index > end:
                    break
                if self._cached_image(index, dimensions) is None:
                    self._remember_image(index, dimensions, self._image_from_frame(frame, dimensions))
                    warmed += 1
        except Exception:
            return warmed
        finally:
            if container is not None:
                try:
                    container.close()
                except Exception:
                    pass
        return warmed

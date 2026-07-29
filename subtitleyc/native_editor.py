from __future__ import annotations

import argparse
import io
import json
import os
import sys
import threading
import time
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import av
from PIL import Image, ImageDraw, ImageFont, ImageTk


@dataclass
class Cue:
    start_seconds: float
    end_seconds: float
    text: str


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


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    configured = os.environ.get("SUBTITLEYC_DATA_DIR")
    if configured:
        return Path(configured)
    if getattr(sys, "frozen", False):
        for env_name in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env_name)
            if base:
                return Path(base) / "SubtitleYC" / "workspace"
    return _runtime_root() / "workspace"


def _bounded_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        value = default
    return max(min_value, min(max_value, value))


def _preview_cache_dir(session_id: str) -> Path:
    return _default_data_dir() / "previews" / session_id


class NativeEditor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.base_url = args.base_url.rstrip("/")
        self.session_id = args.session_id
        self.result_path = Path(args.result)
        self.session = self._fetch_json(f"/api/videos/{self.session_id}")
        self.video_path = self.session["video_path"]
        self.metadata = self.session.get("metadata") or {}
        self.decoder = NativeVideoDecoder(
            self.video_path,
            self.metadata,
            preview_cache_dir=_preview_cache_dir(self.session_id),
            cache_limit=_bounded_int_env("SUBTITLEYC_NATIVE_FRAME_CACHE_LIMIT", 240, 30, 2000),
        )
        self.frame_index = self.decoder.frame_index_for_time(float(args.time_seconds or 0.0))
        self.cues: list[Cue] = []
        self.subtitle_format = self.session.get("subtitle_format") or "srt"
        self.subtitle_dirty = False
        self.crop = self._initial_crop(args.crop_json)
        self.drag_start: tuple[int, int] | None = None
        self.image_rect = (0, 0, 1, 1)
        self.photo: ImageTk.PhotoImage | None = None
        self.playing = False
        self.last_render = 0.0
        self.updating_slider = False
        self.updating_cue_selection = False
        self.warm_after_id: str | None = None
        self.warm_stop = threading.Event()
        self.warm_thread: threading.Thread | None = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("SubtitleYC Smooth Editor")
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        self._load_cues()
        self.root.update_idletasks()
        self._warm_initial_frames()
        self.render()
        self.root.deiconify()

    def _url(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _fetch_json(self, path: str, method: str = "GET", payload: Any | None = None) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._url(path), data=data, headers=headers, method=method)
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _warm_radius(self, seconds: float = 4.0) -> int:
        frame_radius = int(max(12, round(self.decoder.fps * seconds)))
        return min(frame_radius, max(12, self.decoder.cache_limit // 2))

    def _warm_initial_frames(self) -> None:
        if not hasattr(self, "status_var"):
            return
        radius = min(max(12, int(round(self.decoder.fps * 1.5))), max(12, self.decoder.cache_limit // 3))
        self.status_var.set("Preparing smooth preview...")
        self.decoder.warm_frames(
            self.frame_index - radius,
            self.frame_index + radius,
            self.canvas_size(),
            self.warm_stop,
        )
        self.status_var.set("Ready")

    def queue_warmup(self) -> None:
        if not hasattr(self, "root"):
            return
        if self.warm_after_id is not None:
            try:
                self.root.after_cancel(self.warm_after_id)
            except tk.TclError:
                pass
        self.warm_after_id = self.root.after(140, self.start_warmup)

    def start_warmup(self) -> None:
        self.warm_after_id = None
        if not hasattr(self, "canvas"):
            return
        if self.warm_thread is not None and self.warm_thread.is_alive():
            self.warm_stop.set()
        self.warm_stop = threading.Event()
        center = int(self.frame_index)
        radius = self._warm_radius()
        display_size = self.canvas_size()
        stop_event = self.warm_stop
        self.warm_thread = threading.Thread(
            target=lambda: self.decoder.warm_frames(center - radius, center + radius, display_size, stop_event),
            name="SubtitleYCSmoothPreviewWarmup",
            daemon=True,
        )
        self.warm_thread.start()

    def stop_warmup(self) -> None:
        if self.warm_after_id is not None:
            try:
                self.root.after_cancel(self.warm_after_id)
            except tk.TclError:
                pass
            self.warm_after_id = None
        self.warm_stop.set()
        thread = self.warm_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    def _initial_crop(self, crop_json: str | None) -> dict[str, int]:
        if crop_json:
            try:
                crop = json.loads(crop_json)
                return self._clamp_crop(crop)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        width = int(self.metadata.get("width") or 1280)
        height = int(self.metadata.get("height") or 720)
        return self._clamp_crop({
            "x": round(width * 0.08),
            "y": round(height * 0.68),
            "width": round(width * 0.84),
            "height": round(height * 0.2),
        })

    def _clamp_crop(self, crop: dict[str, Any]) -> dict[str, int]:
        width = max(1, int(self.metadata.get("width") or 1))
        height = max(1, int(self.metadata.get("height") or 1))
        x = max(0, min(width - 1, int(round(float(crop.get("x") or 0)))))
        y = max(0, min(height - 1, int(round(float(crop.get("y") or 0)))))
        crop_w = max(1, min(width - x, int(round(float(crop.get("width") or width)))))
        crop_h = max(1, min(height - y, int(round(float(crop.get("height") or height)))))
        return {"x": x, "y": y, "width": crop_w, "height": crop_h}

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=0)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=10)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(left, bg="#111827", highlightthickness=1, highlightbackground="#243244")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_down)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_up)
        self.canvas.bind("<Configure>", lambda _event: self.render())

        controls = ttk.Frame(left)
        controls.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(2, weight=1)
        self.play_button = ttk.Button(controls, text="Play", command=self.toggle_play, width=8)
        self.play_button.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(controls, text="Prev Frame", command=lambda: self.seek_frame(self.frame_index - 1)).grid(row=0, column=1, padx=(0, 6))
        self.slider = ttk.Scale(controls, from_=0, to=max(1, self.decoder.frame_count - 1), orient="horizontal", command=self.on_slider)
        self.slider.grid(row=0, column=2, sticky="ew", padx=(0, 6))
        ttk.Button(controls, text="Next Frame", command=lambda: self.seek_frame(self.frame_index + 1)).grid(row=0, column=3)

        bottom = ttk.Frame(left)
        bottom.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        self.info_label = ttk.Label(bottom, text="Frame: 0 / 0 | Time: 00:00 / 00:00")
        self.info_label.grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Use Crop", command=self.write_result).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bottom, text="Close", command=self.close).grid(row=0, column=2, padx=(8, 0))

        side = ttk.Frame(self.root, padding=(0, 10, 10, 10), width=320)
        side.grid(row=0, column=1, sticky="ns")
        side.rowconfigure(2, weight=1)
        ttk.Label(side, text="Subtitles").grid(row=0, column=0, columnspan=4, sticky="w")
        self.cue_list = tk.Listbox(side, height=18, width=42, exportselection=False)
        self.cue_list.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(6, 8))
        self.cue_list.bind("<<ListboxSelect>>", self.on_cue_select)

        ttk.Button(side, text="Prev", command=self.previous_subtitle).grid(row=3, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(side, text="Next", command=self.next_subtitle).grid(row=3, column=1, sticky="ew", padx=(0, 4))
        ttk.Button(side, text="Reload", command=self._load_cues).grid(row=3, column=2, sticky="ew", padx=(0, 4))
        ttk.Button(side, text="Save", command=self.save_cues).grid(row=3, column=3, sticky="ew")

        timing = ttk.Frame(side)
        timing.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 4))
        timing.columnconfigure(1, weight=1)
        timing.columnconfigure(3, weight=1)
        ttk.Label(timing, text="Start").grid(row=0, column=0, sticky="w")
        self.start_var = tk.StringVar()
        ttk.Entry(timing, textvariable=self.start_var, width=9).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(timing, text="End").grid(row=0, column=2, sticky="w")
        self.end_var = tk.StringVar()
        ttk.Entry(timing, textvariable=self.end_var, width=9).grid(row=0, column=3, sticky="ew", padx=(4, 0))

        nudge = ttk.Frame(side)
        nudge.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        for col in range(4):
            nudge.columnconfigure(col, weight=1)
        ttk.Button(nudge, text="Start -", command=lambda: self.nudge_selected("start", -1)).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(nudge, text="Start +", command=lambda: self.nudge_selected("start", 1)).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ttk.Button(nudge, text="End -", command=lambda: self.nudge_selected("end", -1)).grid(row=0, column=2, sticky="ew", padx=(0, 4))
        ttk.Button(nudge, text="End +", command=lambda: self.nudge_selected("end", 1)).grid(row=0, column=3, sticky="ew")

        self.text_box = tk.Text(side, height=5, width=42, wrap="word")
        self.text_box.grid(row=6, column=0, columnspan=4, sticky="ew")
        ttk.Button(side, text="Apply Cue Edit", command=self.apply_cue_edit).grid(row=7, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(side, textvariable=self.status_var, wraplength=300).grid(row=8, column=0, columnspan=4, sticky="ew", pady=(12, 0))

    def _load_cues(self) -> None:
        try:
            payload = self._fetch_json(f"/api/videos/{self.session_id}/subtitles")
        except HTTPError as exc:
            if exc.code == 404:
                self.cues = []
                self.refresh_cue_list()
                return
            self.status_var.set(f"Subtitle load failed: {exc}")
            return
        except (URLError, TimeoutError, OSError) as exc:
            self.status_var.set(f"Subtitle load failed: {exc}")
            return
        self.subtitle_format = payload.get("subtitle_format") or self.subtitle_format
        self.cues = [
            Cue(float(item.get("start_seconds") or 0), float(item.get("end_seconds") or 0), str(item.get("text") or ""))
            for item in payload.get("cues", [])
        ]
        self.subtitle_dirty = False
        self.refresh_cue_list()

    def save_cues(self) -> None:
        self.apply_cue_edit(silent=True)
        payload = {
            "subtitle_format": self.subtitle_format,
            "cues": [cue.__dict__ for cue in self.cues if cue.text.strip()],
        }
        try:
            self._fetch_json(f"/api/videos/{self.session_id}/subtitles", method="PUT", payload=payload)
            self.subtitle_dirty = False
            self.status_var.set("Subtitles saved")
        except Exception as exc:  # noqa: BLE001 - show editor save failures in the native window.
            self.status_var.set(f"Subtitle save failed: {exc}")

    def refresh_cue_list(self) -> None:
        self.cue_list.delete(0, tk.END)
        for index, cue in enumerate(self.cues, start=1):
            text = cue.text.strip().replace("\n", " ")
            if len(text) > 34:
                text = text[:31] + "..."
            self.cue_list.insert(tk.END, f"{index:03d}  {self.format_time(cue.start_seconds)} -> {self.format_time(cue.end_seconds)}  {text}")
        self.highlight_current_cue()

    def selected_index(self) -> int | None:
        selection = self.cue_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        return index if 0 <= index < len(self.cues) else None

    def select_cue_index(self, index: int, *, scroll: bool = True) -> None:
        if not 0 <= index < len(self.cues):
            return
        self.updating_cue_selection = True
        try:
            self.cue_list.selection_clear(0, tk.END)
            self.cue_list.selection_set(index)
            if scroll:
                self.cue_list.see(index)
        finally:
            self.updating_cue_selection = False

    def on_cue_select(self, _event: Any = None) -> None:
        if self.updating_cue_selection:
            return
        index = self.selected_index()
        if index is None:
            return
        cue = self.cues[index]
        self.start_var.set(f"{cue.start_seconds:.3f}")
        self.end_var.set(f"{cue.end_seconds:.3f}")
        self.text_box.delete("1.0", tk.END)
        self.text_box.insert("1.0", cue.text)
        self.seek_time(cue.start_seconds)

    def apply_cue_edit(self, silent: bool = False) -> None:
        index = self.selected_index()
        if index is None:
            return
        cue = self.cues[index]
        try:
            start = max(0.0, float(self.start_var.get() or cue.start_seconds))
            end = max(start + 0.001, float(self.end_var.get() or cue.end_seconds))
        except ValueError:
            if not silent:
                self.status_var.set("Invalid cue time")
            return
        cue.start_seconds = start
        cue.end_seconds = end
        cue.text = self.text_box.get("1.0", tk.END).strip()
        self.cues.sort(key=lambda item: (item.start_seconds, item.end_seconds))
        self.subtitle_dirty = True
        self.refresh_cue_list()
        self.render()
        if not silent:
            self.status_var.set("Cue updated")

    def nudge_selected(self, boundary: str, frames: float) -> None:
        index = self.selected_index()
        if index is None:
            self.status_var.set("Select a cue first")
            return
        cue = self.cues[index]
        delta = frames / self.decoder.fps
        if boundary == "start":
            cue.start_seconds = max(0.0, min(cue.end_seconds - 0.001, cue.start_seconds + delta))
        else:
            cue.end_seconds = max(cue.start_seconds + 0.001, cue.end_seconds + delta)
        self.start_var.set(f"{cue.start_seconds:.3f}")
        self.end_var.set(f"{cue.end_seconds:.3f}")
        self.subtitle_dirty = True
        self.refresh_cue_list()
        self.render()

    def current_cue_index(self) -> int | None:
        current = self.decoder.frame_time(self.frame_index)
        for index, cue in enumerate(self.cues):
            if cue.start_seconds <= current <= cue.end_seconds:
                return index
        return None

    def highlight_current_cue(self) -> None:
        index = self.current_cue_index()
        if index is None or not self.cues:
            return
        current_selection = self.selected_index()
        self.select_cue_index(index)
        if current_selection == index or self.root.focus_get() == self.text_box:
            return
        cue = self.cues[index]
        self.start_var.set(f"{cue.start_seconds:.3f}")
        self.end_var.set(f"{cue.end_seconds:.3f}")
        self.text_box.delete("1.0", tk.END)
        self.text_box.insert("1.0", cue.text)

    def next_subtitle(self) -> None:
        current = self.decoder.frame_time(self.frame_index)
        for index, cue in enumerate(self.cues):
            if current < cue.start_seconds:
                self.select_cue_index(index)
                self.seek_time(cue.start_seconds)
                return
            if cue.start_seconds <= current < cue.end_seconds:
                self.select_cue_index(index)
                self.seek_time(cue.end_seconds)
                return

    def previous_subtitle(self) -> None:
        current = self.decoder.frame_time(self.frame_index)
        for index in range(len(self.cues) - 1, -1, -1):
            cue = self.cues[index]
            if cue.start_seconds < current <= cue.end_seconds:
                self.select_cue_index(index)
                self.seek_time(cue.start_seconds)
                return
            if cue.end_seconds < current:
                self.select_cue_index(index)
                self.seek_time(cue.end_seconds)
                return

    def canvas_size(self) -> tuple[int, int]:
        return max(2, self.canvas.winfo_width()), max(2, self.canvas.winfo_height())

    def source_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        image_x, image_y, image_w, image_h = self.image_rect
        source_w = max(1, int(self.metadata.get("width") or 1))
        source_h = max(1, int(self.metadata.get("height") or 1))
        return image_x + (x / source_w) * image_w, image_y + (y / source_h) * image_h

    def canvas_to_source(self, x: float, y: float) -> tuple[int, int]:
        image_x, image_y, image_w, image_h = self.image_rect
        source_w = max(1, int(self.metadata.get("width") or 1))
        source_h = max(1, int(self.metadata.get("height") or 1))
        rel_x = 0 if image_w <= 0 else (x - image_x) / image_w
        rel_y = 0 if image_h <= 0 else (y - image_y) / image_h
        return max(0, min(source_w, round(rel_x * source_w))), max(0, min(source_h, round(rel_y * source_h)))

    def render(self) -> None:
        if not hasattr(self, "canvas"):
            return
        now = time.monotonic()
        if now - self.last_render < 0.002:
            pass
        self.last_render = now
        display_size = self.canvas_size()
        try:
            image, frame_index = self.decoder.get_frame(self.frame_index, display_size)
            self.frame_index = frame_index
        except Exception as exc:  # noqa: BLE001 - native editor should stay open and report decode errors.
            self.status_var.set(f"Preview failed: {exc}")
            return

        canvas_w, canvas_h = display_size
        image_w, image_h = image.size
        image_x = (canvas_w - image_w) // 2
        image_y = (canvas_h - image_h) // 2
        self.image_rect = (image_x, image_y, image_w, image_h)

        composed = Image.new("RGB", (canvas_w, canvas_h), "#111827")
        composed.paste(image, (image_x, image_y))
        draw = ImageDraw.Draw(composed, "RGBA")
        crop = self.crop
        x1, y1 = self.source_to_canvas(crop["x"], crop["y"])
        x2, y2 = self.source_to_canvas(crop["x"] + crop["width"], crop["y"] + crop["height"])
        draw.rectangle((x1, y1, x2, y2), outline=(20, 184, 166, 240), width=2)
        draw.rectangle((x1, y1, x2, y2), fill=(20, 184, 166, 35))

        cue_index = self.current_cue_index()
        if cue_index is not None:
            text = self.cues[cue_index].text.strip()
            if text:
                self._draw_subtitle(draw, text, canvas_w, canvas_h)

        self.photo = ImageTk.PhotoImage(composed)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.updating_slider = True
        try:
            self.slider.set(self.frame_index)
        finally:
            self.updating_slider = False
        self.update_info()
        self.highlight_current_cue()
        self.queue_warmup()

    def _draw_subtitle(self, draw: ImageDraw.ImageDraw, text: str, canvas_w: int, canvas_h: int) -> None:
        lines = [line.strip() for line in text.splitlines() if line.strip()] or [text]
        try:
            font = ImageFont.truetype("arial.ttf", max(18, canvas_w // 42))
        except OSError:
            font = ImageFont.load_default()
        line_boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=2) for line in lines]
        line_heights = [box[3] - box[1] for box in line_boxes]
        total_h = sum(line_heights) + 6 * max(0, len(lines) - 1)
        y = canvas_h - total_h - 32
        for line, box, line_h in zip(lines, line_boxes, line_heights):
            line_w = box[2] - box[0]
            x = (canvas_w - line_w) / 2
            draw.rounded_rectangle((x - 14, y - 7, x + line_w + 14, y + line_h + 9), radius=7, fill=(0, 0, 0, 145))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 220))
            y += line_h + 6

    def format_time(self, seconds: float) -> str:
        safe = max(0.0, float(seconds or 0.0))
        minutes = int(safe // 60)
        secs = int(safe % 60)
        millis = int(round((safe - int(safe)) * 1000))
        return f"{minutes:02d}:{secs:02d}.{millis:03d}"

    def update_info(self) -> None:
        total = max(1, self.decoder.frame_count)
        current = self.frame_index + 1
        current_time = self.decoder.frame_time(self.frame_index)
        duration = self.decoder.duration
        self.info_label.configure(text=f"Frame: {current} / {total} | Time: {self.format_time(current_time)} / {self.format_time(duration)}")

    def on_slider(self, value: str) -> None:
        if not hasattr(self, "slider") or self.updating_slider:
            return
        self.stop_playback(update_button=True)
        self.frame_index = self.decoder.clamp_frame(float(value))
        self.render()

    def seek_frame(self, frame_index: int) -> None:
        self.stop_playback(update_button=True)
        self.frame_index = self.decoder.clamp_frame(frame_index)
        self.render()

    def seek_time(self, seconds: float) -> None:
        self.seek_frame(self.decoder.frame_index_for_time(seconds))

    def toggle_play(self) -> None:
        if self.playing:
            self.stop_playback(update_button=True)
        else:
            self.playing = True
            self.play_button.configure(text="Pause")
            self.tick_playback()

    def stop_playback(self, update_button: bool = False) -> None:
        self.playing = False
        if update_button and hasattr(self, "play_button"):
            self.play_button.configure(text="Play")

    def tick_playback(self) -> None:
        if not self.playing:
            return
        self.frame_index = self.decoder.clamp_frame(self.frame_index + 1)
        self.render()
        if self.frame_index >= max(0, self.decoder.frame_count - 1):
            self.stop_playback(update_button=True)
            return
        delay = max(12, int(1000 / min(max(self.decoder.fps, 1), 30)))
        self.root.after(delay, self.tick_playback)

    def on_canvas_down(self, event: Any) -> None:
        self.stop_playback(update_button=True)
        self.drag_start = self.canvas_to_source(event.x, event.y)

    def on_canvas_drag(self, event: Any) -> None:
        if self.drag_start is None:
            return
        start_x, start_y = self.drag_start
        end_x, end_y = self.canvas_to_source(event.x, event.y)
        self.crop = self._clamp_crop({
            "x": min(start_x, end_x),
            "y": min(start_y, end_y),
            "width": abs(end_x - start_x),
            "height": abs(end_y - start_y),
        })
        self.render()

    def on_canvas_up(self, _event: Any) -> None:
        self.drag_start = None

    def write_result(self) -> None:
        payload = {
            "ok": True,
            "crop": self.crop,
            "time_seconds": self.decoder.frame_time(self.frame_index),
            "subtitles_saved": not self.subtitle_dirty,
        }
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        self.result_path.write_text(json.dumps(payload), encoding="utf-8")
        self.status_var.set("Crop sent back to SubtitleYC")

    def close(self) -> None:
        self.stop_warmup()
        if self.subtitle_dirty:
            self.save_cues()
        self.write_result()
        self.decoder.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SubtitleYC native smooth preview/editor")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--crop-json", default="")
    parser.add_argument("--time-seconds", type=float, default=0.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        editor = NativeEditor(parse_args(argv))
        editor.run()
        return 0
    except Exception as exc:  # noqa: BLE001 - write diagnosable failure for the launcher.
        args = parse_args(argv)
        Path(args.result).parent.mkdir(parents=True, exist_ok=True)
        Path(args.result).write_text(json.dumps({"ok": False, "message": str(exc)}), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

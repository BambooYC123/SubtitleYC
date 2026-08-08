
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image
from PySide6.QtCore import QObject, QEvent, QPoint, QRect, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPalette, QPen, QPixmap, QRegion
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QStyle, QTabBar, QTabWidget, QToolButton, QWidget

from .native_video import NativeVideoDecoder


BRIDGE_SCRIPT = r"""
(function () {
  if (window.subtitleycQtBridgeInstalling || (window.pywebview && window.pywebview.api && window.pywebview.api.update_native_preview)) return;
  window.subtitleycQtBridgeInstalling = true;

  function finishInstall() {
    if (!window.qt || !window.qt.webChannelTransport || typeof QWebChannel === "undefined") {
      window.subtitleycQtBridgeInstalling = false;
      return;
    }
    new QWebChannel(window.qt.webChannelTransport, function (channel) {
      const bridge = channel.objects.subtitleycBridge;
      const callbacks = new Map();
      let sequence = 0;

      bridge.response.connect(function (requestId, payloadText) {
        const callback = callbacks.get(requestId);
        if (!callback) return;
        callbacks.delete(requestId);
        try {
          callback.resolve(JSON.parse(payloadText || "{}"));
        } catch (error) {
          callback.reject(error);
        }
      });

      function callBridge(name, args) {
        return new Promise(function (resolve, reject) {
          const requestId = String(++sequence);
          callbacks.set(requestId, { resolve, reject });
          try {
            bridge.call(name, JSON.stringify(args || []), requestId);
          } catch (error) {
            callbacks.delete(requestId);
            reject(error);
          }
        });
      }

      const apiNames = [
        "choose_video_file",
        "choose_download_dir",
        "choose_subtitle_save_path",
        "save_subtitle",
        "save_srt",
        "update_native_preview",
        "set_native_preview_visible",
        "open_subtitle_editor",
        "set_shell_theme",
        "set_shell_language",
        "open_file_location"
      ];
      window.pywebview = window.pywebview || {};
      window.pywebview.api = window.pywebview.api || {};
      for (const name of apiNames) {
        window.pywebview.api[name] = function () {
          return callBridge(name, Array.from(arguments));
        };
      }

      window.subtitleycNativePreviewCropChanged = function (crop) {
        window.dispatchEvent(new CustomEvent("subtitleyc-native-preview-crop", { detail: crop }));
      };
      window.subtitleycNativePreviewSubtitleBoxChanged = function (box) {
        window.dispatchEvent(new CustomEvent("subtitleyc-native-preview-subtitle-box", { detail: box }));
      };
      window.subtitleycQtBridgeInstalling = false;
      window.dispatchEvent(new Event("pywebviewready"));
      window.dispatchEvent(new Event("subtitleyc-native-preview-ready"));
    });
  }

  if (typeof QWebChannel === "undefined") {
    const script = document.createElement("script");
    script.src = "qrc:///qtwebchannel/qwebchannel.js";
    script.onload = finishInstall;
    document.head.appendChild(script);
  } else {
    finishInstall();
  }
})();
"""


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


def _asset_path(name: str) -> Path | None:
    roots: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]
    if getattr(sys, "frozen", False):
        runtime_root = Path(sys.executable).resolve().parent
        roots.extend([runtime_root, runtime_root / "_internal"])
    roots.append(Path(__file__).resolve().parent.parent)

    for root in roots:
        candidate = root / "assets" / name
        if candidate.is_file():
            return candidate
    return None


def _restore_startup_cursor() -> None:
    app = QApplication.instance()
    if app is None:
        return
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def _bring_window_to_front(window: QMainWindow) -> None:
    window.show()
    window.raise_()
    window.activateWindow()


def _clear_startup_topmost(window: QMainWindow) -> None:
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    _bring_window_to_front(window)

def _theme_background(theme: str) -> str:
    return "#eef2f6" if theme == "light" else "#0d131a"


def _apply_webview_theme(web: QWebEngineView, theme: str) -> None:
    background = _theme_background(theme)
    web.setStyleSheet(f"background-color: {background};")
    web.page().setBackgroundColor(QColor(background))


def _preview_cache_dir(session_id: str) -> Path:
    return _default_data_dir() / "previews" / session_id


def _bounded_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        value = default
    return max(min_value, min(max_value, value))


def _qimage_from_pil(image: Image.Image) -> QImage:
    rgb = image.convert("RGB")
    width, height = rgb.size
    data = rgb.tobytes("raw", "RGB")
    return QImage(data, width, height, width * 3, QImage.Format.Format_RGB888).copy()


class NativePreviewSurface(QWidget):
    crop_changed = Signal(str)
    subtitle_box_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.session_id = ""
        self.session: dict[str, Any] | None = None
        self.metadata: dict[str, Any] = {}
        self.decoder: NativeVideoDecoder | None = None
        self.frame_index = 0
        self.crop: dict[str, int] | None = None
        self.show_crop = True
        self.subtitle_text = ""
        self.subtitle_box: dict[str, float] | None = None
        self.subtitle_box_rect = QRect()
        self.subtitle_drag_offset: tuple[int, int] | None = None
        self.pixmap: QPixmap | None = None
        self.image_rect = QRect(0, 0, 1, 1)
        self.drag_start: tuple[int, int] | None = None
        self.last_error = ""
        self.cache_idle_limit = _bounded_int_env("SUBTITLEYC_NATIVE_FRAME_CACHE_IDLE_LIMIT", 60, 30, 1000)
        self.cache_active_limit = _bounded_int_env("SUBTITLEYC_NATIVE_FRAME_CACHE_ACTIVE_LIMIT", 180, self.cache_idle_limit, 3000)
        self.cache_shrink_delay_ms = _bounded_int_env("SUBTITLEYC_NATIVE_FRAME_CACHE_SHRINK_MS", 8000, 1000, 60000)
        self.cache_shrink_timer = QTimer(self)
        self.cache_shrink_timer.setSingleShot(True)
        self.cache_shrink_timer.timeout.connect(self._shrink_decoder_cache)
        self.hide()

    def _shrink_decoder_cache(self) -> None:
        self._set_decoder_cache_limit(self.cache_idle_limit)

    def _set_decoder_cache_limit(self, limit: int) -> None:
        if self.decoder is None:
            return
        setter = getattr(self.decoder, "set_cache_limit", None)
        if callable(setter):
            setter(limit)

    def _set_cache_active(self, active: bool) -> None:
        if self.decoder is None:
            return
        if active:
            self._set_decoder_cache_limit(self.cache_active_limit)
            self.cache_shrink_timer.start(self.cache_shrink_delay_ms)
        elif not self.cache_shrink_timer.isActive():
            self._set_decoder_cache_limit(self.cache_idle_limit)

    def close_decoder(self) -> None:
        self.cache_shrink_timer.stop()
        decoder = self.decoder
        self.decoder = None
        if decoder is not None:
            decoder.close()

    def set_session(self, session: dict[str, Any] | None) -> None:
        next_id = str(session.get("id") if session else "")
        if next_id == self.session_id:
            return
        self.close_decoder()
        self.session_id = next_id
        self.session = session
        self.metadata = dict(session.get("metadata") or {}) if session else {}
        self.pixmap = None
        self.last_error = ""
        if not session:
            self.hide()
            self.update()
            return
        video_path = str(session.get("video_path") or "")
        self.decoder = NativeVideoDecoder(
            video_path,
            self.metadata,
            preview_cache_dir=_preview_cache_dir(self.session_id),
            cache_limit=self.cache_idle_limit,
        )
        if not self.isVisible():
            self.show()

    def configure(self, payload: dict[str, Any], session: dict[str, Any] | None) -> None:
        rect = payload.get("rect") or {}
        width = max(1, int(round(float(rect.get("width") or 1))))
        height = max(1, int(round(float(rect.get("height") or 1))))
        left = int(round(float(rect.get("left") or 0)))
        top = int(round(float(rect.get("top") or 0)))
        next_geometry = QRect(left, top, width, height)
        geometry_changed = self.geometry() != next_geometry
        if geometry_changed:
            self.setGeometry(next_geometry)
        self._apply_occlusion_mask(payload, width, height, left, top)

        previous_session_id = self.session_id
        self.set_session(session)
        if not self.decoder:
            return
        session_changed = self.session_id != previous_session_id
        if not self.isVisible():
            self.show()
        if geometry_changed or session_changed:
            self.raise_()
        self._set_cache_active(str(payload.get("cache_mode") or "").casefold() == "active")
        crop = payload.get("crop")
        self.crop = self._clamp_crop(crop) if isinstance(crop, dict) else self.crop
        self.show_crop = bool(payload.get("show_crop", True))
        self.subtitle_text = str(payload.get("subtitle_text") or "")
        self.subtitle_box = self._normalized_subtitle_box(payload.get("subtitle_box"))
        next_frame_index = self.decoder.frame_index_for_time(float(payload.get("time_seconds") or 0.0))
        frame_changed = next_frame_index != self.frame_index
        session_changed = self.session_id != previous_session_id
        self.frame_index = next_frame_index
        if session_changed or geometry_changed or frame_changed or self.pixmap is None:
            self.update_frame()
        else:
            self.update()

    def _apply_occlusion_mask(self, payload: dict[str, Any], width: int, height: int, left: int, top: int) -> None:
        occluders = payload.get("occluders") or []
        if not isinstance(occluders, list) or not occluders:
            self.clearMask()
            return

        bounds = QRect(0, 0, width, height)
        region = QRegion(bounds)
        masked = False
        for occluder in occluders:
            if not isinstance(occluder, dict):
                continue
            try:
                rect = QRect(
                    int(round(float(occluder.get("left") or 0))) - left,
                    int(round(float(occluder.get("top") or 0))) - top,
                    max(0, int(round(float(occluder.get("width") or 0)))),
                    max(0, int(round(float(occluder.get("height") or 0)))),
                ).intersected(bounds)
            except (TypeError, ValueError):
                continue
            if rect.isEmpty():
                continue
            region = region.subtracted(QRegion(rect))
            masked = True

        if masked:
            self.setMask(region)
        else:
            self.clearMask()

    def _source_size(self) -> tuple[int, int]:
        width = max(1, int(self.metadata.get("width") or 1))
        height = max(1, int(self.metadata.get("height") or 1))
        return width, height

    def _clamp_crop(self, crop: dict[str, Any]) -> dict[str, int]:
        source_w, source_h = self._source_size()
        x = max(0, min(source_w - 1, int(round(float(crop.get("x") or 0)))))
        y = max(0, min(source_h - 1, int(round(float(crop.get("y") or 0)))))
        width = max(1, min(source_w - x, int(round(float(crop.get("width") or source_w)))))
        height = max(1, min(source_h - y, int(round(float(crop.get("height") or source_h)))))
        return {"x": x, "y": y, "width": width, "height": height}

    def update_frame(self) -> None:
        if not self.decoder or self.width() <= 1 or self.height() <= 1:
            return
        try:
            image, frame_index = self.decoder.get_frame(self.frame_index, (self.width(), self.height()))
            self.frame_index = frame_index
            self.pixmap = QPixmap.fromImage(_qimage_from_pil(image))
            self.last_error = ""
        except Exception as exc:  # noqa: BLE001 - surface decode failures in the preview panel.
            self.last_error = str(exc)
        self.update()

    def resizeEvent(self, _event: Any) -> None:  # noqa: N802 - Qt override name.
        if self.decoder:
            QTimer.singleShot(0, self.update_frame)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt override name.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111827"))
        if self.last_error:
            painter.setPen(QColor("#cbd5e1"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.last_error)
            return
        if not self.pixmap:
            painter.setPen(QColor("#cbd5e1"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load a video")
            return

        x = (self.width() - self.pixmap.width()) // 2
        y = (self.height() - self.pixmap.height()) // 2
        self.image_rect = QRect(x, y, self.pixmap.width(), self.pixmap.height())
        painter.drawPixmap(self.image_rect, self.pixmap)
        self._draw_crop(painter)
        self._draw_subtitle(painter)

    def _draw_crop(self, painter: QPainter) -> None:
        if not self.show_crop or not self.crop:
            return
        rect = self._crop_to_widget(self.crop)
        painter.fillRect(rect, QColor(20, 184, 166, 36))
        pen = QPen(QColor(20, 184, 166, 240), 2)
        painter.setPen(pen)
        painter.drawRect(rect)

    def _normalized_subtitle_box(self, value: Any) -> dict[str, float] | None:
        if not isinstance(value, dict):
            return None
        try:
            left = float(value.get("left", 0.5))
            top = float(value.get("top", 1.0))
        except (TypeError, ValueError):
            return None
        return {
            "left": max(0.0, min(1.0, left)),
            "top": max(0.0, min(1.0, top)),
        }

    def _subtitle_rect_for_size(self, width: int, height: int) -> QRect:
        image_rect = self.image_rect if not self.image_rect.isEmpty() else self.rect()
        max_left = max(0, image_rect.width() - width)
        max_top = max(0, image_rect.height() - height)
        if self.subtitle_box:
            x = image_rect.x() + round(float(self.subtitle_box.get("left", 0.5)) * max_left)
            y = image_rect.y() + round(float(self.subtitle_box.get("top", 1.0)) * max_top)
        else:
            x = image_rect.x() + max_left // 2
            y = image_rect.y() + max(0, image_rect.height() - height - 28)
        return QRect(x, y, width, height)

    def _set_subtitle_box_from_widget(self, x: int, y: int) -> None:
        image_rect = self.image_rect if not self.image_rect.isEmpty() else self.rect()
        box_rect = self.subtitle_box_rect
        max_left = max(0, image_rect.width() - box_rect.width())
        max_top = max(0, image_rect.height() - box_rect.height())
        left = 0.5 if max_left <= 0 else (x - image_rect.x()) / max_left
        top = 1.0 if max_top <= 0 else (y - image_rect.y()) / max_top
        self.subtitle_box = {
            "left": round(max(0.0, min(1.0, left)), 6),
            "top": round(max(0.0, min(1.0, top)), 6),
        }
        self.subtitle_box_changed.emit(json.dumps(self.subtitle_box))

    def _wrap_subtitle_line(self, line: str, metrics: Any, max_width: int) -> list[str]:
        text = line.strip()
        if not text:
            return []
        if metrics.horizontalAdvance(text) <= max_width:
            return [text]

        wrapped: list[str] = []
        words = text.split(" ")
        if len(words) > 1:
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if metrics.horizontalAdvance(candidate) <= max_width:
                    current = candidate
                    continue
                if current:
                    wrapped.append(current)
                    current = ""
                if metrics.horizontalAdvance(word) <= max_width:
                    current = word
                else:
                    wrapped.extend(self._wrap_subtitle_line_by_character(word, metrics, max_width))
            if current:
                wrapped.append(current)
            return wrapped

        return self._wrap_subtitle_line_by_character(text, metrics, max_width)

    def _wrap_subtitle_line_by_character(self, text: str, metrics: Any, max_width: int) -> list[str]:
        wrapped: list[str] = []
        current = ""
        for char in text:
            candidate = f"{current}{char}"
            if current and metrics.horizontalAdvance(candidate) > max_width:
                wrapped.append(current)
                current = char
            else:
                current = candidate
        if current:
            wrapped.append(current)
        return wrapped or [text]

    def _wrap_subtitle_lines(self, lines: list[str], metrics: Any, max_width: int) -> list[str]:
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(self._wrap_subtitle_line(line, metrics, max_width))
        return wrapped or lines
    def _draw_subtitle(self, painter: QPainter) -> None:
        text = self.subtitle_text.strip()
        if not text:
            self.subtitle_box_rect = QRect()
            return
        lines = [line.strip() for line in text.splitlines() if line.strip()] or [text]
        font = QFont("Arial", max(14, self.width() // 44), QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        line_height = metrics.height()
        line_gap = 4
        image_width = max(1, self.image_rect.width() if not self.image_rect.isEmpty() else self.width())
        max_line_width = max(20, image_width - 52)
        lines = self._wrap_subtitle_lines(lines, metrics, max_line_width)
        total_text_height = len(lines) * line_height + max(0, len(lines) - 1) * line_gap
        max_text_width = max(metrics.horizontalAdvance(line) for line in lines)
        box_width = min(max(1, image_width - 24), max_text_width + 28)
        box_height = total_text_height + 10
        box = self._subtitle_rect_for_size(box_width, box_height)
        self.subtitle_box_rect = box
        painter.fillRect(box, QColor(0, 0, 0, 150))
        y = box.y() + 5
        painter.setPen(QColor("#ffffff"))
        for line in lines:
            text_width = metrics.horizontalAdvance(line)
            x = box.x() + max(0, (box.width() - text_width) // 2)
            painter.drawText(x, y + metrics.ascent(), line)
            y += line_height + line_gap

    def _crop_to_widget(self, crop: dict[str, int]) -> QRect:
        source_w, source_h = self._source_size()
        rect = self.image_rect
        x = rect.x() + round((crop["x"] / source_w) * rect.width())
        y = rect.y() + round((crop["y"] / source_h) * rect.height())
        width = round((crop["width"] / source_w) * rect.width())
        height = round((crop["height"] / source_h) * rect.height())
        return QRect(x, y, max(1, width), max(1, height))

    def _widget_to_source(self, x: int, y: int) -> tuple[int, int]:
        source_w, source_h = self._source_size()
        rect = self.image_rect
        rel_x = 0.0 if rect.width() <= 0 else (x - rect.x()) / rect.width()
        rel_y = 0.0 if rect.height() <= 0 else (y - rect.y()) / rect.height()
        return (
            max(0, min(source_w, round(rel_x * source_w))),
            max(0, min(source_h, round(rel_y * source_h))),
        )

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name.
        if event.button() == Qt.MouseButton.LeftButton and self.decoder:
            position = event.position()
            x = round(position.x())
            y = round(position.y())
            if not self.subtitle_box_rect.isEmpty() and self.subtitle_box_rect.contains(QPoint(x, y)):
                self.subtitle_drag_offset = (x - self.subtitle_box_rect.x(), y - self.subtitle_box_rect.y())
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            if self.show_crop:
                self.drag_start = self._widget_to_source(x, y)

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name.
        position = event.position()
        x = round(position.x())
        y = round(position.y())
        if self.subtitle_drag_offset is not None and not self.subtitle_box_rect.isEmpty():
            offset_x, offset_y = self.subtitle_drag_offset
            image_rect = self.image_rect if not self.image_rect.isEmpty() else self.rect()
            max_x = image_rect.x() + max(0, image_rect.width() - self.subtitle_box_rect.width())
            max_y = image_rect.y() + max(0, image_rect.height() - self.subtitle_box_rect.height())
            next_x = max(image_rect.x(), min(max_x, x - offset_x))
            next_y = max(image_rect.y(), min(max_y, y - offset_y))
            self.subtitle_box_rect.moveTo(next_x, next_y)
            self._set_subtitle_box_from_widget(next_x, next_y)
            self.update()
            return
        if self.drag_start is None:
            if not self.subtitle_box_rect.isEmpty() and self.subtitle_box_rect.contains(QPoint(x, y)):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            return
        end_x, end_y = self._widget_to_source(x, y)
        start_x, start_y = self.drag_start
        self.crop = self._clamp_crop({
            "x": min(start_x, end_x),
            "y": min(start_y, end_y),
            "width": abs(end_x - start_x),
            "height": abs(end_y - start_y),
        })
        self.crop_changed.emit(json.dumps(self.crop))
        self.update()

    def mouseReleaseEvent(self, _event: Any) -> None:  # noqa: N802 - Qt override name.
        self.subtitle_drag_offset = None
        self.drag_start = None
        self.unsetCursor()


BRIDGE_ALLOWED_METHODS = frozenset(
    {
        "choose_video_file",
        "choose_download_dir",
        "choose_subtitle_save_path",
        "save_subtitle",
        "save_srt",
        "update_native_preview",
        "set_native_preview_visible",
        "open_subtitle_editor",
        "set_shell_theme",
        "set_shell_language",
        "open_file_location",
    }
)


def _url_origin(url: QUrl) -> tuple[str, str, int]:
    scheme = url.scheme().casefold()
    default_port = 443 if scheme == "https" else 80
    return scheme, url.host().casefold(), url.port(default_port)


class LocalOnlyRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, base_url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.allowed_origin = _url_origin(QUrl(base_url))

    def interceptRequest(self, info: Any) -> None:  # noqa: N802 - Qt override name.
        url = info.requestUrl()
        if url.scheme().casefold() in {"about", "blob", "data", "qrc"}:
            return
        if _url_origin(url) != self.allowed_origin:
            info.block(True)


def _create_isolated_profile(
    base_url: str,
    parent: QObject,
) -> tuple[QWebEngineProfile, LocalOnlyRequestInterceptor]:
    profile = QWebEngineProfile("SubtitleYC", parent)
    data_dir = _default_data_dir()
    profile_root = (data_dir.parent if getattr(sys, "frozen", False) else data_dir) / "web-profile"
    profile_root.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(profile_root))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    profile.setHttpCacheMaximumSize(32 * 1024 * 1024)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    interceptor = LocalOnlyRequestInterceptor(base_url, profile)
    profile.setUrlRequestInterceptor(interceptor)
    return profile, interceptor


def _harden_web_page(page: QWebEnginePage) -> None:
    settings = page.settings()
    for attribute in (
        QWebEngineSettings.WebAttribute.AllowRunningInsecureContent,
        QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
        QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
        QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
        QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        QWebEngineSettings.WebAttribute.PluginsEnabled,
    ):
        settings.setAttribute(attribute, False)


class LocalOnlyWebPage(QWebEnginePage):
    def __init__(self, base_url: str, profile: QWebEngineProfile, parent: QObject | None = None) -> None:
        super().__init__(profile, parent)
        self.allowed_origin = _url_origin(QUrl(base_url))
        _harden_web_page(self)

    def acceptNavigationRequest(self, url: QUrl, navigation_type: Any, is_main_frame: bool) -> bool:  # noqa: N802
        if url.scheme().casefold() in {"about", "qrc"}:
            return True
        if _url_origin(url) == self.allowed_origin:
            return True
        if is_main_frame and url.scheme().casefold() in {"http", "https"}:
            QDesktopServices.openUrl(url)
        return False

class QtDesktopBridge(QObject):
    response = Signal(str, str)

    def __init__(self, window: "QtDesktopWindow", base_url: str, preview_surface: NativePreviewSurface | None = None) -> None:
        super().__init__()
        self.window = window
        self.base_url = base_url.rstrip("/")
        self.app_token = os.environ.get("SUBTITLEYC_API_TOKEN", "")
        self.preview_surface = preview_surface
        self.session_cache: dict[str, dict[str, Any]] = {}

    def _tr(self, english: str, chinese: str) -> str:
        return chinese if self.window.shell_language == "zh-CN" else english

    @Slot(str, str, str)
    def call(self, name: str, args_json: str, request_id: str) -> None:
        try:
            if name not in BRIDGE_ALLOWED_METHODS:
                raise PermissionError("Unknown desktop bridge method.")
            args = json.loads(args_json or "[]")
            if not isinstance(args, list):
                raise ValueError("Desktop bridge arguments must be a list.")
            method = getattr(self, name)
            result = method(*args)
        except Exception as exc:  # noqa: BLE001 - bridge failures need to return to JS.
            result = {"ok": False, "message": str(exc)}
        self.response.emit(request_id, json.dumps(result))

    def _url(self, path: str) -> str:
        candidate = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        base = urllib.parse.urlsplit(self.base_url)
        parsed = urllib.parse.urlsplit(candidate)
        if (parsed.scheme.casefold(), parsed.netloc.casefold()) != (base.scheme.casefold(), base.netloc.casefold()):
            raise PermissionError("Desktop bridge URL must stay inside SubtitleYC.")
        return candidate

    def _request(self, path: str) -> urllib.request.Request:
        return urllib.request.Request(
            self._url(path),
            headers={"X-SubtitleYC-Token": self.app_token},
        )

    def _fetch_json(self, path: str) -> dict[str, Any]:
        with urllib.request.urlopen(self._request(path), timeout=30) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _session(self, session_id: str) -> dict[str, Any] | None:
        if not session_id:
            return None
        cached = self.session_cache.get(session_id)
        if cached:
            return cached
        session = self._fetch_json(f"/api/videos/{session_id}")
        self.session_cache[session_id] = session
        return session

    def choose_video_file(self, current_path: str = "") -> dict[str, object]:
        start_dir = Path(os.path.expandvars(current_path or "")).expanduser() if current_path else Path.home()
        if not start_dir.is_dir():
            videos_dir = Path.home() / "Videos"
            start_dir = videos_dir if videos_dir.is_dir() else Path.home()
        selected, _filter = QFileDialog.getOpenFileName(
            self.window,
            self._tr("Open video file", "打开视频文件"),
            str(start_dir),
            self._tr(
                "Video files (*.mp4 *.mkv *.webm *.mov *.m4v *.avi);;All files (*.*)",
                "视频文件 (*.mp4 *.mkv *.webm *.mov *.m4v *.avi);;所有文件 (*.*)",
            ),
        )
        if not selected:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": str(Path(selected))}
    def choose_download_dir(self, current_path: str = "") -> dict[str, object]:
        start_dir = Path(os.path.expandvars(current_path or "")).expanduser() if current_path else Path.home()
        if not start_dir.is_dir():
            downloads_dir = Path.home() / "Downloads"
            start_dir = downloads_dir if downloads_dir.is_dir() else Path.home()
        selection = QFileDialog.getExistingDirectory(
            self.window,
            self._tr("Choose download folder", "选择下载文件夹"),
            str(start_dir),
        )
        if not selection:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": str(Path(selection))}

    def choose_subtitle_save_path(self, suggested_name: str = "subtitles.srt") -> dict[str, object]:
        safe_name = Path(suggested_name or "subtitles.srt").name
        if Path(safe_name).suffix.casefold() != ".srt":
            safe_name = f"{Path(safe_name).stem or 'subtitles'}.srt"
        selected, _filter = QFileDialog.getSaveFileName(
            self.window,
            self._tr("Save subtitle file", "保存字幕文件"),
            str(Path.home() / safe_name),
            self._tr("SubRip subtitles (*.srt);;All files (*.*)", "SubRip 字幕 (*.srt);;所有文件 (*.*)"),
        )
        if not selected:
            return {"ok": False, "cancelled": True}
        target = Path(selected)
        if target.suffix.casefold() != ".srt":
            target = target.with_suffix(".srt")
        return {"ok": True, "path": str(target)}

    def open_file_location(self, target_path: str = "") -> dict[str, object]:
        if not target_path:
            return {"ok": False, "message": "No folder path is available."}
        target = Path(os.path.expandvars(target_path)).expanduser()
        if not target.exists():
            return {"ok": False, "message": f"Location does not exist: {target}"}
        folder = target if target.is_dir() else target.parent
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        return {"ok": bool(opened), "path": str(folder), "message": "Opened location" if opened else "Could not open location."}

    def save_srt(self, srt_url: str, suggested_name: str = "subtitles.srt") -> dict[str, object]:
        return self.save_subtitle(srt_url, suggested_name)

    def save_subtitle(self, subtitle_url: str, suggested_name: str = "subtitles.srt") -> dict[str, object]:
        if not subtitle_url:
            return {"ok": False, "message": "No subtitle file is available yet."}
        safe_name = Path(suggested_name or "subtitles.srt").name
        suffix = Path(safe_name).suffix.casefold() or ".srt"
        filters = {
            ".srt": self._tr("SubRip subtitles (*.srt)", "SubRip 字幕 (*.srt)"),
            ".txt": self._tr("Plain text subtitles (*.txt)", "纯文本字幕 (*.txt)"),
            ".ass": self._tr("Advanced SubStation Alpha (*.ass)", "Advanced SubStation Alpha 字幕 (*.ass)"),
        }
        file_filter = filters.get(
            suffix,
            self._tr("Subtitle files (*.srt *.txt *.ass)", "字幕文件 (*.srt *.txt *.ass)"),
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self.window,
            self._tr("Save subtitles", "保存字幕"),
            str(Path.home() / safe_name),
            f"{file_filter};;{self._tr('All files (*.*)', '所有文件 (*.*)')}",
        )
        if not selected:
            return {"ok": False, "cancelled": True}
        target = Path(selected)
        if target.suffix.casefold() != suffix:
            target = target.with_suffix(suffix)
        with urllib.request.urlopen(self._request(subtitle_url), timeout=30) as response:
            target.write_bytes(response.read())
        return {"ok": True, "path": str(target), "format": suffix.lstrip(".")}

    def _target_preview(self) -> NativePreviewSurface:
        return self.preview_surface or self.window.preview

    def update_native_preview(self, payload: dict[str, Any] | None = None) -> dict[str, object]:
        payload = payload or {}
        session_id = str(payload.get("session_id") or "")
        session = self._session(session_id)
        self._target_preview().configure(payload, session)
        return {"ok": True, "native_preview": True}

    def set_native_preview_visible(self, visible: bool = True) -> dict[str, object]:
        target = self._target_preview()
        next_visible = bool(visible)
        if target.isVisible() != next_visible:
            target.setVisible(next_visible)
        return {"ok": True}

    def open_subtitle_editor(self, session_id: str = "", time_seconds: float = 0.0) -> dict[str, object]:
        self.window.open_subtitle_editor_tab(str(session_id or ""), float(time_seconds or 0.0))
        return {"ok": True}
    def set_shell_theme(self, theme: str = "dark") -> dict[str, object]:
        self.window.apply_shell_theme(str(theme or "dark"))
        return {"ok": True, "theme": self.window.shell_theme}

    def set_shell_language(self, language: str = "en") -> dict[str, object]:
        self.window.apply_shell_language(str(language or "en"))
        return {"ok": True, "language": self.window.shell_language}


class EditorPreviewTab(QWidget):
    def __init__(self, window: "QtDesktopWindow", session_id: str) -> None:
        super().__init__(window.tabs)
        self.window = window
        self.session_id = session_id
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.web = QWebEngineView(self)
        self.web.setPage(LocalOnlyWebPage(window.base_url, window.web_profile, self.web))
        self.web.hide()
        self.apply_theme(window.shell_theme)
        self.preview = NativePreviewSurface(self)
        self.preview.raise_()
        self.bridge = QtDesktopBridge(window, window.base_url, self.preview)
        self.channel = QWebChannel(self.web.page())
        self.channel.registerObject("subtitleycBridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.preview.subtitle_box_changed.connect(self.on_preview_subtitle_box_changed)
        self.web.loadFinished.connect(self.install_bridge)
        self.web.setGeometry(self.rect())

    def install_bridge(self, _ok: bool = True) -> None:
        self.web.page().runJavaScript(BRIDGE_SCRIPT)
        self.web.show()
        QTimer.singleShot(0, self.sync_geometry)

    def apply_theme(self, theme: str) -> None:
        background = _theme_background(theme)
        self.setStyleSheet(f"background-color: {background};")
        _apply_webview_theme(self.web, theme)

    def sync_geometry(self) -> None:
        self.web.setGeometry(self.rect())
        self.preview.raise_()
        self.web.page().runJavaScript("window.subtitleycSyncNativePreview && window.subtitleycSyncNativePreview();")

    def set_editor_url(self, url: str) -> None:
        self.web.hide()
        self.apply_theme(self.window.shell_theme)
        self.web.setUrl(QUrl(url))

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name.
        super().resizeEvent(event)
        QTimer.singleShot(0, self.sync_geometry)

    def on_preview_subtitle_box_changed(self, box_json: str) -> None:
        script = f"window.subtitleycNativePreviewSubtitleBoxChanged && window.subtitleycNativePreviewSubtitleBoxChanged({box_json});"
        self.web.page().runJavaScript(script)

    def close_preview(self) -> None:
        self.preview.close_decoder()

class QtDesktopWindow(QMainWindow):
    def __init__(self, url: str, on_ready: Any = None) -> None:
        super().__init__()
        parsed_url = urllib.parse.urlsplit(url)
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}".rstrip("/")
        self.on_ready = on_ready
        self.ready_notified = False
        self.editor_tabs: dict[str, EditorPreviewTab] = {}
        self.setWindowTitle("SubtitleYC")
        self.resize(1280, 840)
        self.setMinimumSize(980, 680)

        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(False)
        self.tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.tabs.tabBar().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.shell_theme = "dark"
        self.shell_language = "en"
        self.apply_shell_theme("dark")
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_current_tab_changed)
        self.setCentralWidget(self.tabs)

        self.container = QWidget(self.tabs)
        main_tab_index = self.tabs.addTab(self.container, "SubtitleYC")
        self.tabs.tabBar().setTabButton(main_tab_index, QTabBar.ButtonPosition.LeftSide, None)
        self.tabs.tabBar().setTabButton(main_tab_index, QTabBar.ButtonPosition.RightSide, None)
        self.container.installEventFilter(self)
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.container.setStyleSheet(f"background-color: {_theme_background(self.shell_theme)};")
        self.web_profile, self.web_request_interceptor = _create_isolated_profile(self.base_url, self)
        self.web = QWebEngineView(self.container)
        self.web.setPage(LocalOnlyWebPage(self.base_url, self.web_profile, self.web))
        self.web.hide()
        _apply_webview_theme(self.web, self.shell_theme)
        self.preview = NativePreviewSurface(self.container)
        self.preview.raise_()
        self.bridge = QtDesktopBridge(self, url)
        self.channel = QWebChannel(self.web.page())
        self.channel.registerObject("subtitleycBridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.preview.crop_changed.connect(self.on_preview_crop_changed)
        self.preview.subtitle_box_changed.connect(self.on_preview_subtitle_box_changed)
        self.web.loadFinished.connect(self.install_bridge)
        self.web.setGeometry(self.container.rect())
        self.web.load(url)
        QTimer.singleShot(0, self.sync_main_view_geometry)
    def install_bridge(self, _ok: bool = True) -> None:
        self.web.page().runJavaScript(BRIDGE_SCRIPT)
        self.web.show()
        QTimer.singleShot(0, self.sync_main_view_geometry)
        QTimer.singleShot(150, _restore_startup_cursor)
        QTimer.singleShot(150, self.notify_ready)

    def notify_ready(self) -> None:
        if self.ready_notified:
            return
        self.ready_notified = True
        if callable(self.on_ready):
            self.on_ready()

    def sync_main_view_geometry(self) -> None:
        if not hasattr(self, "web"):
            return
        self.web.setGeometry(self.container.rect())
        if self.tabs.currentWidget() is self.container:
            self.preview.raise_()
            self.web.page().runJavaScript("window.subtitleycSyncNativePreview && window.subtitleycSyncNativePreview();")

    def eventFilter(self, watched: QObject, event: Any) -> bool:  # noqa: N802 - Qt override name.
        if watched is getattr(self, "container", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self.sync_main_view_geometry)
        return super().eventFilter(watched, event)

    def apply_shell_theme(self, theme: str = "dark") -> None:
        self.shell_theme = "light" if theme == "light" else "dark"
        if self.shell_theme == "light":
            colors = {
                "app_bg": "#eef2f6",
                "row_bg": "#eef2f6",
                "tab_bg": "#eef2f6",
                "active_bg": "#ffffff",
                "hover_bg": "#f8fafb",
                "line": "#d7dee7",
                "text": "#1f2328",
                "muted": "#66707c",
            }
        else:
            colors = {
                "app_bg": "#0d131a",
                "row_bg": "#141c25",
                "tab_bg": "#141c25",
                "active_bg": "#192331",
                "hover_bg": "#192331",
                "line": "#2b3948",
                "text": "#e7edf5",
                "muted": "#98a6b7",
            }
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {colors['row_bg']};
            }}
            QComboBox,
            QAbstractItemView,
            QMenu {{
                background: {colors['tab_bg']};
                color: {colors['text']};
                border: 1px solid {colors['line']};
                selection-background-color: {colors['hover_bg']};
                selection-color: {colors['text']};
            }}
            """
        )
        app = QApplication.instance()
        if app is not None:
            palette = QPalette(app.palette())
            palette.setColor(QPalette.ColorRole.Window, QColor(colors["app_bg"]))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
            palette.setColor(QPalette.ColorRole.Base, QColor(colors["tab_bg"]))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["row_bg"]))
            palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
            palette.setColor(QPalette.ColorRole.Button, QColor(colors["tab_bg"]))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["hover_bg"]))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["text"]))
            app.setPalette(palette)
        self.tabs.setStyleSheet(
            f"""
            QTabWidget {{
                background: {colors['row_bg']};
            }}
            QTabWidget::pane {{
                border: 0;
                border-top: 1px solid {colors['line']};
                background: {colors['app_bg']};
                top: -1px;
            }}
            QTabWidget::tab-bar {{
                alignment: left;
            }}
            QTabBar {{
                background: {colors['row_bg']};
                border-bottom: 1px solid {colors['line']};
            }}
            QTabBar::tab {{
                width: 158px;
                min-width: 158px;
                max-width: 158px;
                min-height: 22px;
                padding: 4px 12px;
                margin: 4px 2px 0 2px;
                border: 1px solid transparent;
                border-bottom-color: {colors['line']};
                border-top-left-radius: 9px;
                border-top-right-radius: 9px;
                background: {colors['tab_bg']};
                color: {colors['muted']};
                font-weight: 700;
            }}
            QTabBar::tab:hover {{
                background: {colors['hover_bg']};
                border-color: {colors['line']};
                border-bottom-color: {colors['line']};
                color: {colors['text']};
            }}
            QTabBar::tab:selected {{
                background: {colors['active_bg']};
                border-color: {colors['line']};
                border-bottom-color: {colors['active_bg']};
                color: {colors['text']};
            }}
            QTabBar::close-button {{
                width: 14px;
                height: 14px;
                margin: 0 7px 0 4px;
                subcontrol-position: right;
            }}
            QToolButton#subtitleycTabCloseButton {{
                width: 20px;
                height: 20px;
                margin: 0 6px 0 2px;
                padding: 0;
                border: 0;
                border-radius: 4px;
                background: transparent;
            }}
            QToolButton#subtitleycTabCloseButton:hover {{
                background: {colors['hover_bg']};
            }}
            """
        )
        if hasattr(self, "container"):
            self.container.setStyleSheet(f"background-color: {colors['app_bg']};")
        if hasattr(self, "web"):
            _apply_webview_theme(self.web, self.shell_theme)

        theme_json = json.dumps(self.shell_theme)
        script = f"window.subtitleycApplyExternalTheme && window.subtitleycApplyExternalTheme({theme_json});"
        for editor in list(self.editor_tabs.values()):
            editor.apply_theme(self.shell_theme)
            editor.web.page().runJavaScript(script)

    def apply_shell_language(self, language: str = "en") -> None:
        self.shell_language = "zh-CN" if language == "zh-CN" else "en"
        editor_label = "SubtitleYC 编辑器" if self.shell_language == "zh-CN" else "SubtitleYC Editor"
        close_label = "关闭 SubtitleYC 编辑器" if self.shell_language == "zh-CN" else "Close SubtitleYC Editor"
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if widget is self.container:
                self.tabs.setTabText(index, "SubtitleYC")
                continue
            if isinstance(widget, EditorPreviewTab):
                self.tabs.setTabText(index, editor_label)
                button = self.tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
                if isinstance(button, QToolButton):
                    button.setToolTip(close_label)
                    button.setAccessibleName(close_label)
        language_json = json.dumps(self.shell_language)
        script = f"window.subtitleycApplyExternalLanguage && window.subtitleycApplyExternalLanguage({language_json});"
        for editor in list(self.editor_tabs.values()):
            editor.web.page().runJavaScript(script)

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.container:
            return
        for key, editor in list(self.editor_tabs.items()):
            if editor is widget:
                editor.close_preview()
                del self.editor_tabs[key]
        self.tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()

    def _make_tab_close_button(self, editor: EditorPreviewTab) -> QToolButton:
        button = QToolButton(self.tabs.tabBar())
        button.setObjectName("subtitleycTabCloseButton")
        button.setAutoRaise(True)
        button.setFixedSize(28, 20)
        button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close_label = "关闭 SubtitleYC 编辑器" if self.shell_language == "zh-CN" else "Close SubtitleYC Editor"
        button.setToolTip(close_label)
        button.setAccessibleName(close_label)
        button.clicked.connect(lambda _checked=False: self.close_tab(self.tabs.indexOf(editor)))
        return button

    def on_current_tab_changed(self, _index: int) -> None:
        widget = self.tabs.currentWidget()
        if widget is self.container:
            self.sync_main_view_geometry()
            return
        self.preview.hide()
        if isinstance(widget, EditorPreviewTab):
            widget.sync_geometry()

    def open_subtitle_editor_tab(self, session_id: str = "", time_seconds: float = 0.0) -> None:
        clean_session_id = str(session_id or "")
        key = f"subtitle-editor:{clean_session_id or 'empty'}"
        editor = self.editor_tabs.get(key)
        if editor is None or self.tabs.indexOf(editor) < 0:
            editor = EditorPreviewTab(self, clean_session_id)
            self.editor_tabs[key] = editor
            editor_label = "SubtitleYC 编辑器" if self.shell_language == "zh-CN" else "SubtitleYC Editor"
            tab_index = self.tabs.addTab(editor, editor_label)
            close_button = self._make_tab_close_button(editor)
            self.tabs.tabBar().setTabButton(tab_index, QTabBar.ButtonPosition.RightSide, close_button)
        else:
            tab_index = self.tabs.indexOf(editor)
        if clean_session_id:
            query = urllib.parse.urlencode({"session": clean_session_id, "time": f"{float(time_seconds or 0.0):.6f}"})
            editor.set_editor_url(f"{self.base_url}/editor?{query}")
        else:
            editor.set_editor_url(f"{self.base_url}/editor")
        self.tabs.setCurrentIndex(tab_index)
        QTimer.singleShot(0, editor.sync_geometry)
    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name.
        super().resizeEvent(event)
        QTimer.singleShot(0, self.sync_main_view_geometry)

    def on_preview_crop_changed(self, crop_json: str) -> None:
        script = f"window.subtitleycNativePreviewCropChanged && window.subtitleycNativePreviewCropChanged({crop_json});"
        self.web.page().runJavaScript(script)

    def on_preview_subtitle_box_changed(self, box_json: str) -> None:
        script = f"window.subtitleycNativePreviewSubtitleBoxChanged && window.subtitleycNativePreviewSubtitleBoxChanged({box_json});"
        self.web.page().runJavaScript(script)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override name.
        self.preview.close_decoder()
        for editor in list(self.editor_tabs.values()):
            editor.close_preview()
        self.web_profile.cookieStore().deleteAllCookies()
        self.web_profile.clearHttpCache()
        super().closeEvent(event)

def run_qt_desktop(url: str, on_ready: Any = None) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    icon_path = _asset_path("SubtitleYC.ico")
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    window = QtDesktopWindow(url, on_ready=on_ready)
    if icon_path:
        window.setWindowIcon(QIcon(str(icon_path)))
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    _bring_window_to_front(window)
    QTimer.singleShot(250, lambda: _bring_window_to_front(window))
    QTimer.singleShot(900, lambda: _clear_startup_topmost(window))
    QTimer.singleShot(10000, _restore_startup_cursor)
    QTimer.singleShot(10000, window.notify_ready)
    app.exec()

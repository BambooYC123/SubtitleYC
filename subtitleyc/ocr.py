from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from .srt import SubtitleCue


ProgressCallback = Callable[[float, str], None]
CJK_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
CJK_SPACE_PATTERN = re.compile(r"(?<=[\u3400-\u9fff\uf900-\ufaff])\s+(?=[\u3400-\u9fff\uf900-\ufaff])")
_OPENCC = None


@dataclass(frozen=True)
class CropArea:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class OCRSettings:
    crop: CropArea
    language: str = "eng"
    frame_step: int = 1
    min_confidence: int = 65
    similarity: float = 0.72
    max_gap_frames: int = 0
    merge_gap_seconds: float = 0.0
    psm: int = 7
    oem: int = 3
    threshold: str = "subtitle"
    scale: int = 2
    start_seconds: float = 0.0
    end_seconds: float | None = None
    tessdata_dir: str | None = None
    brightness_threshold: int | None = None
    ssim_threshold: float = 0.88
    max_image_width: int = 1280
    min_subtitle_duration: float = 0.04
    normalize_chinese: bool = True


@dataclass
class _ActiveCue:
    start_frame: int
    last_seen_frame: int
    frame_step: int
    samples: dict[str, tuple[int, float]] = field(default_factory=dict)

    def add(self, text: str, confidence: float, frame_index: int) -> None:
        count, total_confidence = self.samples.get(text, (0, 0.0))
        self.samples[text] = (count + 1, total_confidence + confidence)
        self.last_seen_frame = frame_index

    @property
    def text(self) -> str:
        if not self.samples:
            return ""
        return max(
            self.samples.items(),
            key=lambda item: (item[1][0], item[1][1] / max(item[1][0], 1), len(item[0])),
        )[0]


def normalize_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = CJK_SPACE_PATTERN.sub("", text)
    return text.strip(" \t\r\n-_|「」『』")


def language_uses_cjk(language: str) -> bool:
    parts = re.split(r"[+\s,;]+", language.casefold())
    return any(part.startswith(("chi", "jpn", "kor")) for part in parts)




def simplify_chinese(text: str) -> str:
    global _OPENCC
    if not text:
        return text
    if _OPENCC is False:
        return text
    if _OPENCC is None:
        try:
            from opencc import OpenCC
        except ImportError:
            _OPENCC = False
            return text
        _OPENCC = OpenCC("t2s")
    return _OPENCC.convert(text)


def postprocess_text(text: str, settings: OCRSettings) -> str:
    text = normalize_text(text)
    if settings.normalize_chinese and language_uses_cjk(settings.language):
        text = simplify_chinese(text)
    return text

def text_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.casefold(), right.casefold()).ratio()


def _clamp_crop(crop: CropArea, frame_width: int, frame_height: int) -> CropArea:
    x = max(0, min(crop.x, max(frame_width - 1, 0)))
    y = max(0, min(crop.y, max(frame_height - 1, 0)))
    width = max(1, min(crop.width, frame_width - x))
    height = max(1, min(crop.height, frame_height - y))
    return CropArea(x=x, y=y, width=width, height=height)


def _preprocess(frame, crop: CropArea, settings: OCRSettings):
    import cv2

    clipped = _clamp_crop(crop, frame.shape[1], frame.shape[0])
    cropped = frame[clipped.y : clipped.y + clipped.height, clipped.x : clipped.x + clipped.width]
    if cropped.size == 0:
        return cropped

    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    if settings.brightness_threshold is not None:
        _, gray = cv2.threshold(gray, settings.brightness_threshold, 255, cv2.THRESH_TOZERO)

    scale = max(1.0, float(settings.scale))
    if settings.max_image_width > 0:
        scale = min(scale, settings.max_image_width / max(gray.shape[1], 1))
    if scale != 1.0:
        gray = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    if settings.threshold == "adaptive":
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        processed = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
    elif settings.threshold == "subtitle":
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel)
    elif settings.threshold == "otsu":
        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        processed = gray

    if processed.mean() < 127:
        processed = cv2.bitwise_not(processed)
    return processed



def image_similarity(left, right) -> float:
    import cv2

    if left is None or right is None or left.size == 0 or right.size == 0:
        return 0.0
    if left.shape != right.shape:
        right = cv2.resize(right, (left.shape[1], left.shape[0]), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(left, right)
    return max(0.0, min(1.0, 1.0 - float(diff.mean()) / 255.0))

def _ocr_frame(frame, settings: OCRSettings) -> tuple[str, float]:
    import pytesseract
    from pytesseract import Output

    image = _preprocess(frame, settings.crop, settings)
    if image.size == 0:
        return "", 0.0

    config = (
        f"--oem {settings.oem} --psm {settings.psm} "
        "-c preserve_interword_spaces=1"
    )
    data = pytesseract.image_to_data(
        image,
        lang=settings.language,
        config=config,
        output_type=Output.DICT,
    )

    words: list[str] = []
    confidences: list[float] = []
    for word, confidence in zip(data.get("text", []), data.get("conf", []), strict=False):
        clean_word = word.strip()
        if not clean_word:
            continue
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            continue
        if confidence_value >= settings.min_confidence:
            words.append(clean_word)
            confidences.append(confidence_value)

    text = postprocess_text(" ".join(words), settings)
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    raw_text = ""
    if language_uses_cjk(settings.language) and (not text or not CJK_PATTERN.search(text)):
        raw_text = postprocess_text(
            pytesseract.image_to_string(
                image,
                lang=settings.language,
                config=config,
            ),
            settings,
        )
    if raw_text and (not text or len(raw_text) > len(text)):
        return raw_text, average_confidence

    return text, average_confidence


def _merge_cues(cues: list[SubtitleCue], similarity: float, merge_gap_seconds: float) -> list[SubtitleCue]:
    merged: list[SubtitleCue] = []
    for cue in cues:
        if not cue.text.strip():
            continue
        if (
            merged
            and cue.start_seconds - merged[-1].end_seconds <= merge_gap_seconds
            and text_similarity(cue.text, merged[-1].text) >= similarity
        ):
            previous = merged[-1]
            text = cue.text if len(cue.text) > len(previous.text) else previous.text
            merged[-1] = SubtitleCue(
                start_seconds=previous.start_seconds,
                end_seconds=max(previous.end_seconds, cue.end_seconds),
                text=text,
            )
        else:
            merged.append(cue)
    return merged


def run_video_ocr(
    video_path: Path,
    settings: OCRSettings,
    progress: ProgressCallback | None = None,
) -> list[SubtitleCue]:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    if fps <= 0:
        raise RuntimeError("Video FPS could not be detected")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    start_frame = max(0, int(settings.start_seconds * fps))
    end_frame = frame_count - 1 if settings.end_seconds is None else int(settings.end_seconds * fps)
    if frame_count > 0:
        end_frame = min(end_frame, frame_count - 1)
    if end_frame < start_frame:
        raise RuntimeError("OCR end time is before start time")

    frame_step = max(1, settings.frame_step)
    total_to_process = ((end_frame - start_frame) // frame_step) + 1
    processed_count = 0
    cues: list[SubtitleCue] = []
    active: _ActiveCue | None = None
    previous_image = None
    previous_text = ""
    previous_confidence = 0.0

    def close_active() -> None:
        nonlocal active
        if active is None:
            return
        end_frame_exclusive = active.last_seen_frame + frame_step
        start_seconds = active.start_frame / fps
        end_seconds = max(end_frame_exclusive / fps, start_seconds + settings.min_subtitle_duration)
        cues.append(SubtitleCue(start_seconds=start_seconds, end_seconds=end_seconds, text=active.text))
        active = None

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_index = start_frame
    while frame_index <= end_frame:
        ok, frame = cap.read()
        if not ok:
            break

        should_process = (frame_index - start_frame) % frame_step == 0
        if should_process:
            processed_image = _preprocess(frame, settings.crop, settings)
            if (
                previous_image is not None
                and previous_text
                and settings.ssim_threshold > 0
                and image_similarity(previous_image, processed_image) >= settings.ssim_threshold
            ):
                text, confidence = previous_text, previous_confidence
            else:
                text, confidence = _ocr_frame(frame, settings)
                previous_image = processed_image
                previous_text = text
                previous_confidence = confidence
            processed_count += 1

            if text:
                if active and text_similarity(text, active.text) >= settings.similarity:
                    active.add(text, confidence, frame_index)
                else:
                    close_active()
                    active = _ActiveCue(
                        start_frame=frame_index,
                        last_seen_frame=frame_index,
                        frame_step=frame_step,
                    )
                    active.add(text, confidence, frame_index)
            elif active and frame_index - active.last_seen_frame > settings.max_gap_frames:
                close_active()

            if progress and (processed_count == 1 or processed_count % 10 == 0 or processed_count == total_to_process):
                ratio = processed_count / total_to_process
                progress(ratio, f"OCR frame {processed_count} of {total_to_process}")

        frame_index += 1

    cap.release()
    close_active()
    return _merge_cues(cues, settings.similarity, settings.merge_gap_seconds)

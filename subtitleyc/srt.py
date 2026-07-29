from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleCue:
    start_seconds: float
    end_seconds: float
    text: str


_SRT_TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
_ASS_TAG_RE = re.compile(r"\{[^}]*\}")


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _parse_srt_timestamp(value: str) -> float:
    clock, fraction = value.replace(",", ".").split(".", 1)
    hours, minutes, seconds = [int(part) for part in clock.split(":")]
    millis = int((fraction + "000")[:3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _parse_ass_timestamp(value: str) -> float:
    clock, fraction = value.strip().replace(",", ".").split(".", 1)
    hours, minutes, seconds = [int(part) for part in clock.split(":")]
    centis = int((fraction + "00")[:2])
    return hours * 3600 + minutes * 60 + seconds + centis / 100


def _format_ass_timestamp(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(total_cs, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def parse_srt(srt_text: str) -> list[SubtitleCue]:
    normalized = srt_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    cues: list[SubtitleCue] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        timing_index = -1
        timing_match: re.Match[str] | None = None
        for index, line in enumerate(lines):
            timing_match = _SRT_TIMING_RE.search(line)
            if timing_match:
                timing_index = index
                break
        if timing_index < 0 or timing_match is None:
            continue

        text = "\n".join(lines[timing_index + 1 :]).strip()
        if not text:
            continue
        cues.append(
            SubtitleCue(
                start_seconds=_parse_srt_timestamp(timing_match.group("start")),
                end_seconds=_parse_srt_timestamp(timing_match.group("end")),
                text=text,
            )
        )
    return cues


def _ass_plain_text(value: str) -> str:
    text = value.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
    text = _ASS_TAG_RE.sub("", text)
    return text.strip()


def parse_ass(ass_text: str) -> list[SubtitleCue]:
    lines = ass_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    in_events = False
    format_fields: list[str] = []
    cues: list[SubtitleCue] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            in_events = line.casefold() == "[events]"
            continue
        if not in_events:
            continue

        key, _, value = line.partition(":")
        key = key.strip().casefold()
        if key == "format":
            format_fields = [field.strip().casefold() for field in value.split(",")]
            continue
        if key != "dialogue":
            continue

        fields = format_fields or [
            "layer",
            "start",
            "end",
            "style",
            "name",
            "marginl",
            "marginr",
            "marginv",
            "effect",
            "text",
        ]
        parts = [part.strip() for part in value.split(",", max(0, len(fields) - 1))]
        if len(parts) < len(fields):
            continue
        field_map = dict(zip(fields, parts))
        start_raw = field_map.get("start", "")
        end_raw = field_map.get("end", "")
        text = _ass_plain_text(field_map.get("text", ""))
        if not start_raw or not end_raw or not text:
            continue
        try:
            start = _parse_ass_timestamp(start_raw)
            end = _parse_ass_timestamp(end_raw)
        except (TypeError, ValueError):
            continue
        cues.append(SubtitleCue(start_seconds=start, end_seconds=max(start + 0.001, end), text=text))

    return cues


def adjust_cue_timing(
    cues: list[SubtitleCue],
    offset_seconds: float = 0.0,
    frame_seconds: float | None = None,
) -> list[SubtitleCue]:
    adjusted: list[SubtitleCue] = []
    snap = frame_seconds if frame_seconds and frame_seconds > 0 else None
    for cue in cues:
        start = cue.start_seconds
        end = cue.end_seconds
        if snap:
            start = round(start / snap) * snap
            end = round(end / snap) * snap
        start += offset_seconds
        end += offset_seconds
        start = max(0.0, start)
        end = max(start + 0.001, end)
        adjusted.append(SubtitleCue(start_seconds=start, end_seconds=end, text=cue.text))
    return adjusted


def cues_to_srt(cues: list[SubtitleCue]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        text = cue.text.strip()
        if not text:
            continue
        start = format_timestamp(cue.start_seconds)
        end = format_timestamp(max(cue.end_seconds, cue.start_seconds + 0.001))
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def cues_to_txt(cues: list[SubtitleCue]) -> str:
    lines: list[str] = []
    for cue in cues:
        text = " ".join(part.strip() for part in cue.text.splitlines() if part.strip())
        if text:
            lines.append(text)
    return "\n".join(lines) + ("\n" if lines else "")


def _ass_text(text: str) -> str:
    return text.strip().replace("{", "(").replace("}", ")").replace("\n", r"\N")


def cues_to_ass(cues: list[SubtitleCue], title: str = "SubtitleYC") -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
Title: {title}
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for cue in cues:
        text = _ass_text(cue.text)
        if not text:
            continue
        start = _format_ass_timestamp(cue.start_seconds)
        end = _format_ass_timestamp(max(cue.end_seconds, cue.start_seconds + 0.001))
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return header + "\n".join(events) + ("\n" if events else "")
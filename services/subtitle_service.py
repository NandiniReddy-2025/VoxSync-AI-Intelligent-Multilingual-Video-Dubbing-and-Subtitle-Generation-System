import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import timedelta

def format_timestamp_srt(seconds: float) -> str:
    td = timedelta(seconds=max(0.0, seconds))
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_timestamp_vtt(seconds: float) -> str:
    td = timedelta(seconds=max(0.0, seconds))
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def format_timestamp_ass(seconds: float) -> str:
    td = timedelta(seconds=max(0.0, seconds))
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    centis = int(((seconds - int(seconds)) * 100))
    return f"{hours:01d}:{minutes:02d}:{secs:02d}.{centis:02d}"

def get_segment_subtitle_text(seg: Dict[str, Any], mode: str = "translated") -> str:
    original = (seg.get("original_text") or "").strip()
    translated = (seg.get("translated_text") or "").strip()

    if mode == "original":
        return original or translated
    elif mode == "bilingual":
        if translated and original and translated != original:
            return f"{translated}\n{original}"
        return translated or original
    else:  # "translated"
        return translated or original

def generate_srt_content(segments: List[Dict[str, Any]], mode: str = "translated") -> str:
    """Generate standard SRT string."""
    entries = []
    idx = 1
    for seg in sorted(segments, key=lambda s: s.get("start_time", 0.0)):
        text = get_segment_subtitle_text(seg, mode)
        if not text:
            continue
        start_str = format_timestamp_srt(float(seg["start_time"]))
        end_str = format_timestamp_srt(float(seg["end_time"]))
        entries.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
        idx += 1
    return "\n".join(entries)

def generate_vtt_content(segments: List[Dict[str, Any]], mode: str = "translated") -> str:
    """Generate WebVTT string."""
    entries = ["WEBVTT\n"]
    idx = 1
    for seg in sorted(segments, key=lambda s: s.get("start_time", 0.0)):
        text = get_segment_subtitle_text(seg, mode)
        if not text:
            continue
        start_str = format_timestamp_vtt(float(seg["start_time"]))
        end_str = format_timestamp_vtt(float(seg["end_time"]))
        entries.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
        idx += 1
    return "\n".join(entries)

def hex_to_ass_color(hex_str: str) -> str:
    """Convert #RRGGBB to ASS &H00BBGGRR format."""
    hex_clean = hex_str.lstrip("#")
    if len(hex_clean) == 6:
        r, g, b = hex_clean[0:2], hex_clean[2:4], hex_clean[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"

def generate_ass_content(
    segments: List[Dict[str, Any]],
    settings: Optional[Dict[str, Any]] = None,
    mode: str = "translated"
) -> str:
    """Generate ASS (Advanced SubStation Alpha) subtitle content with custom styles."""
    if not settings:
        settings = {}

    font_family = settings.get("font_family", "Arial")
    font_size = settings.get("font_size", 22)
    primary_color = hex_to_ass_color(settings.get("primary_color", "#FFFFFF"))
    position = settings.get("position", "bottom")

    # Alignment in ASS: 2=bottom-center, 8=top-center, 5=middle-center
    alignment = 2
    if position == "top":
        alignment = 8
    elif position == "middle":
        alignment = 5

    header = f"""[Script Info]
Title: VoxSync AI Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{font_size},{primary_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,{alignment},20,20,25,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = []
    for seg in sorted(segments, key=lambda s: s.get("start_time", 0.0)):
        text = get_segment_subtitle_text(seg, mode)
        if not text:
            continue
        start_ass = format_timestamp_ass(float(seg["start_time"]))
        end_ass = format_timestamp_ass(float(seg["end_time"]))
        ass_text = text.replace("\n", "\\N")
        dialogues.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{ass_text}")

    return header + "\n".join(dialogues)

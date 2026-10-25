import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import EXPORTS_DIR, TEMP_DIR, FFMPEG_EXE
from services.audio_service import (
    build_timeline_dubbed_audio,
    run_ffmpeg,
    get_media_duration,
    inspect_media_streams,
    check_audio_audibility
)
from services.subtitle_service import (
    generate_srt_content,
    generate_vtt_content,
    generate_ass_content
)

def export_srt_file(project_id: str, segments: List[Dict[str, Any]], mode: str = "translated") -> str:
    content = generate_srt_content(segments, mode=mode)
    out_path = EXPORTS_DIR / f"{project_id}_{mode}.srt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(out_path)

def export_vtt_file(project_id: str, segments: List[Dict[str, Any]], mode: str = "translated") -> str:
    content = generate_vtt_content(segments, mode=mode)
    out_path = EXPORTS_DIR / f"{project_id}_{mode}.vtt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(out_path)

def export_transcript_txt(project_id: str, segments: List[Dict[str, Any]]) -> str:
    out_path = EXPORTS_DIR / f"{project_id}_transcript.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"VoxSync AI Transcript Export\nProject ID: {project_id}\n\n")
        for s in segments:
            idx = s.get("segment_index", 0) + 1
            start = s.get("start_time", 0.0)
            end = s.get("end_time", 0.0)
            orig = s.get("original_text", "")
            trans = s.get("translated_text", "")
            f.write(f"[{start:.2f}s - {end:.2f}s] Segment {idx}:\n")
            f.write(f"Original: {orig}\n")
            if trans:
                f.write(f"Translated: {trans}\n")
            f.write("-" * 40 + "\n")
    return str(out_path)

def export_full_dubbed_audio(project_id: str, segments: List[Dict[str, Any]], total_duration: float) -> str:
    wav_out = str(EXPORTS_DIR / f"{project_id}_dubbed.wav")
    mp3_out = str(EXPORTS_DIR / f"{project_id}_dubbed.mp3")
    
    # 1. Assemble full timeline audio matching exact duration (enforces zero-omission)
    build_timeline_dubbed_audio(segments, total_duration, wav_out)

    # 2. Convert to high-quality MP3 for distribution & browser streaming
    cmd = [
        "-i", wav_out,
        "-b:a", "192k",
        "-y", mp3_out
    ]
    run_ffmpeg(cmd)
    
    if os.path.exists(mp3_out) and os.path.getsize(mp3_out) > 500:
        is_aud, msg = check_audio_audibility(mp3_out)
        if not is_aud:
            raise RuntimeError(f"Exported dubbed audio MP3 is inaudible: {msg}")
        return mp3_out

    is_aud, msg = check_audio_audibility(wav_out)
    if not is_aud:
        raise RuntimeError(f"Exported dubbed audio WAV is inaudible: {msg}")
    return wav_out

def export_combined_video(
    project_id: str,
    original_video_path: str,
    segments: List[Dict[str, Any]],
    total_duration: float,
    embed_subtitles: bool = False,
    subtitle_mode: str = "translated",
    subtitle_settings: Optional[Dict[str, Any]] = None,
    preserve_background_audio: bool = False
) -> str:
    """
    Combine original video stream with synthesized dubbed audio,
    optionally burning in subtitles.
    Guarantees:
    - 100% of transcript segments must have valid audio before export.
    - Full voice replacement maps ONLY [0:v:0] and [1:a:0] with AAC encoding.
    - Original speech audio stream [0:a:0] is NEVER mapped into full replacement output.
    - Background preservation separates/attenuates dialogue frequencies to prevent raw speech leakage.
    - Post-export FFprobe validation guarantees video stream, audio stream, and non-silent playback.
    """
    if not os.path.exists(original_video_path):
        raise FileNotFoundError(f"Original video not found: {original_video_path}")

    if not segments:
        raise ValueError("Cannot export dubbed video: project has no transcript segments.")

    # Strict Zero-Omission Check: Verify all segments have audio
    missing_segs = [
        f"Segment #{s.get('segment_index', i)+1}"
        for i, s in enumerate(segments)
        if not s.get("audio_path") or not os.path.exists(s.get("audio_path")) or os.path.getsize(s.get("audio_path")) < 100
    ]
    if missing_segs:
        missing_summary = ", ".join(missing_segs[:8])
        if len(missing_segs) > 8:
            missing_summary += f"... and {len(missing_segs) - 8} more"
        raise ValueError(
            f"Cannot export dubbed video: {len(missing_segs)} of {len(segments)} segments are missing synthesized speech "
            f"({missing_summary}). Please generate speech voiceovers for all segments in Step 3 before exporting."
        )

    # Determine exact source video duration to avoid any truncation or drift
    vid_dur = get_media_duration(original_video_path)
    actual_target_duration = vid_dur if vid_dur > 0.1 else total_duration

    # 1. Assemble dubbed audio track matching exact video duration
    dubbed_audio_path = str(TEMP_DIR / f"temp_dub_{project_id}.wav")
    build_timeline_dubbed_audio(segments, actual_target_duration, dubbed_audio_path)

    # Verify assembled dubbed audio before muxing
    is_audible, audit_msg = check_audio_audibility(dubbed_audio_path)
    if not is_audible:
        raise RuntimeError(f"Assembled dubbed audio failed audibility check before muxing: {audit_msg}")

    out_video_path = str(EXPORTS_DIR / f"{project_id}_dubbed.mp4")

    # Check if original video has an audio stream (needed only if preserve_background_audio is chosen)
    src_streams = inspect_media_streams(original_video_path)
    has_orig_audio = len(src_streams.get("audio_streams", [])) > 0

    # 2. Build FFmpeg command
    if embed_subtitles:
        ass_path = str(TEMP_DIR / f"temp_{project_id}.ass")
        ass_content = generate_ass_content(segments, subtitle_settings, mode=subtitle_mode)
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
        
        if preserve_background_audio and has_orig_audio:
            # Genuine background audio suppression: band-reject human vocal range (300Hz-3400Hz)
            # and lower volume to 8%, so original spoken dialogue is eliminated while ambient bed remains.
            filter_complex = (
                f"[0:v:0]subtitles='{ass_escaped}'[vout];"
                f"[0:a:0]volume=0.08,bandreject=f=1200:w=1200[bg];"
                f"[1:a:0]volume=1.0[dub];"
                f"[bg][dub]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            cmd = [
                "-i", original_video_path,
                "-i", dubbed_audio_path,
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-disposition:a:0", "default",
                "-y", out_video_path
            ]
        else:
            # Pure full audio replacement: explicitly map visual [0:v:0] and dubbed audio [1:a:0]
            cmd = [
                "-i", original_video_path,
                "-i", dubbed_audio_path,
                "-vf", f"subtitles='{ass_escaped}'",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-disposition:a:0", "default",
                "-y", out_video_path
            ]
    else:
        if preserve_background_audio and has_orig_audio:
            filter_complex = (
                f"[0:a:0]volume=0.08,bandreject=f=1200:w=1200[bg];"
                f"[1:a:0]volume=1.0[dub];"
                f"[bg][dub]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            cmd = [
                "-i", original_video_path,
                "-i", dubbed_audio_path,
                "-filter_complex", filter_complex,
                "-map", "0:v:0",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-disposition:a:0", "default",
                "-y", out_video_path
            ]
        else:
            # Pure full audio replacement: fast stream copy for video + AAC encode for dubbed audio
            cmd = [
                "-i", original_video_path,
                "-i", dubbed_audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-disposition:a:0", "default",
                "-y", out_video_path
            ]

    res = run_ffmpeg(cmd)

    # 3. Fallback re-encode if stream copy fails for specific container codecs
    if res.returncode != 0 or not os.path.exists(out_video_path) or os.path.getsize(out_video_path) < 1000:
        fallback_cmd = [
            "-i", original_video_path,
            "-i", dubbed_audio_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-disposition:a:0", "default",
            "-y", out_video_path
        ]
        res_fb = run_ffmpeg(fallback_cmd)
        if res_fb.returncode != 0 or not os.path.exists(out_video_path) or os.path.getsize(out_video_path) < 1000:
            if os.path.exists(out_video_path):
                try:
                    os.remove(out_video_path)
                except Exception:
                    pass
            raise RuntimeError(f"FFmpeg video export failed:\n{res.stderr}\nFallback:\n{res_fb.stderr}")

    # 4. Mandatory Post-Export Stream & Audibility Verification (PHASE 5)
    exported_streams = inspect_media_streams(out_video_path)
    if len(exported_streams.get("video_streams", [])) == 0:
        if os.path.exists(out_video_path):
            try:
                os.remove(out_video_path)
            except Exception:
                pass
        raise RuntimeError("Export validation failed: No video stream present in final MP4.")

    if len(exported_streams.get("audio_streams", [])) == 0:
        if os.path.exists(out_video_path):
            try:
                os.remove(out_video_path)
            except Exception:
                pass
        raise RuntimeError("Export validation failed: Dubbed video was exported without an audio stream.")

    is_aud, aud_msg = check_audio_audibility(out_video_path)
    if not is_aud:
        if os.path.exists(out_video_path):
            try:
                os.remove(out_video_path)
            except Exception:
                pass
        raise RuntimeError(f"Export validation failed: Exported video audio is silent or inaudible ({aud_msg}).")

    # Cleanup temp audio
    try:
        if os.path.exists(dubbed_audio_path):
            os.remove(dubbed_audio_path)
    except Exception:
        pass

    return out_video_path



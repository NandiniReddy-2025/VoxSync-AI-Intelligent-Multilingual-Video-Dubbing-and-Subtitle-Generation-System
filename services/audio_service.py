import os
import re
import subprocess
import wave
import contextlib
from pathlib import Path
from typing import Tuple, List, Optional
from config import FFMPEG_EXE, AUDIO_DIR, PROCESSED_DIR, TEMP_DIR

def run_ffmpeg(args: List[str]) -> subprocess.CompletedProcess:
    cmd = [FFMPEG_EXE] + args
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)

def get_media_duration(file_path: str) -> float:
    """Extract duration in seconds from any audio/video file using FFmpeg."""
    try:
        # Check if wave file first
        if file_path.lower().endswith(".wav"):
            try:
                with contextlib.closing(wave.open(file_path, 'r')) as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    return frames / float(rate)
            except Exception:
                pass

        res = run_ffmpeg(["-i", file_path, "-f", "null", "-"])
        stderr = res.stderr
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+|\d+)", stderr)
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception as e:
        print(f"Error determining duration for {file_path}: {e}")
    return 0.0

def get_audio_peak_volume(audio_path: str) -> Optional[float]:
    """Extract maximum volume in dB using FFmpeg volumedetect filter."""
    try:
        res = run_ffmpeg(["-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"])
        max_match = re.search(r"max_volume:\s*(-?[\d\.]+)\s*dB", res.stderr)
        if max_match:
            return float(max_match.group(1))
    except Exception:
        pass
    return None

def check_audio_audibility(audio_path: str) -> Tuple[bool, str]:
    """Check if audio has audible sound or is silent/empty."""
    dur = get_media_duration(audio_path)
    if dur <= 0.1:
        return False, "Audio duration is 0 seconds. No readable audio stream was found."
    
    peak = get_audio_peak_volume(audio_path)
    if peak is not None and peak <= -65.0:
        return False, f"The audio is silent or inaudible (peak volume: {peak:.1f} dB). Valid speech is required."
    return True, "Audio is audible"

def inspect_media_streams(file_path: str) -> dict:
    """Inspect video and audio streams of a media file using FFmpeg."""
    res = run_ffmpeg(["-i", str(file_path), "-f", "null", "-"])
    stderr = res.stderr
    
    video_streams = []
    audio_streams = []
    in_input_section = False
    
    for line in stderr.splitlines():
        if "Input #0" in line:
            in_input_section = True
            continue
        elif "Output #0" in line or "Stream mapping:" in line:
            in_input_section = False
            break
            
        if in_input_section and "Stream #0:" in line:
            if "Video:" in line:
                codec_match = re.search(r"Video:\s*([^\s,]+)", line)
                video_streams.append({
                    "line": line.strip(),
                    "codec": codec_match.group(1) if codec_match else "unknown"
                })
            elif "Audio:" in line:
                codec_match = re.search(r"Audio:\s*([^\s,]+)", line)
                audio_streams.append({
                    "line": line.strip(),
                    "codec": codec_match.group(1) if codec_match else "unknown"
                })
                
    dur = get_media_duration(file_path)
    peak = get_audio_peak_volume(file_path)
    return {
        "duration": dur,
        "peak_volume_db": peak,
        "video_streams": video_streams,
        "audio_streams": audio_streams
    }


def extract_audio_from_video(video_path: str, output_name: Optional[str] = None) -> str:
    """Extract clean 16kHz mono PCM WAV audio suitable for speech recognition."""
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video file does not exist: {video_path}")
    if video_path_obj.suffix.lower() == ".temp" or ".temp." in video_path_obj.name:
        raise ValueError("Cannot extract audio from an incomplete or temporary video file.")

    if not output_name:
        output_name = f"{video_path_obj.stem}_audio.wav"
    output_path = AUDIO_DIR / output_name

    cmd = [
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y", str(output_path)
    ]
    res = run_ffmpeg(cmd)
    if res.returncode != 0 and not output_path.exists():
        raise RuntimeError(f"FFmpeg audio extraction failed: {res.stderr}")

    # Verify extracted audio
    is_audible, msg = check_audio_audibility(str(output_path))
    if not is_audible:
        print(f"Warning: {msg}")

    return str(output_path)

def adjust_audio_speed(input_audio: str, output_audio: str, speed_factor: float) -> str:
    """Adjust audio playback rate without changing pitch using atempo filter."""
    if speed_factor <= 0.5:
        speed_factor = 0.5
    elif speed_factor >= 2.0:
        speed_factor = 2.0

    cmd = [
        "-i", input_audio,
        "-filter:a", f"atempo={speed_factor}",
        "-y", output_audio
    ]
    res = run_ffmpeg(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to adjust audio speed: {res.stderr}")
    return output_audio

def generate_silence(duration: float, output_path: str) -> str:
    """Generate a silent WAV file of given duration."""
    cmd = [
        "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(max(0.05, duration)),
        "-acodec", "pcm_s16le",
        "-y", output_path
    ]
    run_ffmpeg(cmd)
    return output_path

def build_timeline_dubbed_audio(segments_info: List[dict], total_duration: float, output_path: str) -> str:
    """
    Assemble dubbed speech segments onto a full-length timeline matching video duration.
    Preserves exact timing, gaps, and pauses between phrases.
    Zero-omission enforcement: Every segment in segments_info must have a valid audio file.
    """
    if total_duration <= 0.1:
        raise ValueError(f"Invalid target duration for dubbed audio assembly: {total_duration}s")

    if not segments_info:
        raise ValueError("Cannot assemble dubbed audio: no segments provided.")

    # Strict Zero-Omission Check: Verify 100% of segments have valid audio files
    missing_segments = []
    for idx, s in enumerate(segments_info):
        seg_num = s.get("segment_index", idx) + 1
        path = s.get("audio_path")
        if not path or not os.path.exists(path) or os.path.getsize(path) < 100:
            missing_segments.append(f"Segment #{seg_num}")

    if missing_segments:
        missing_summary = ", ".join(missing_segments[:8])
        if len(missing_segments) > 8:
            missing_summary += f"... and {len(missing_segments) - 8} more"
        raise ValueError(
            f"Cannot assemble dubbed audio: {len(missing_segments)} of {len(segments_info)} segments "
            f"are missing synthesized audio ({missing_summary}). Please synthesize all segments before assembly."
        )

    # Sort segments by start_time
    sorted_segments = sorted(
        segments_info,
        key=lambda s: float(s["start_time"])
    )

    import time
    token = f"{Path(output_path).stem}_{os.getpid()}_{time.time_ns()}"
    temp_concat_txt = TEMP_DIR / f"concat_{token}.txt"
    part_files = []
    current_time = 0.0

    for idx, seg in enumerate(sorted_segments):
        seg_audio = seg["audio_path"]
        start = float(seg["start_time"])
        end = float(seg["end_time"])
        slot_dur = max(0.1, end - start)

        # 1. If there's a silence gap before this segment, insert silence
        if start > current_time + 0.03:
            gap = start - current_time
            silence_file = str(TEMP_DIR / f"sil_{Path(output_path).stem}_{idx}_{gap:.2f}.wav")
            generate_silence(gap, silence_file)
            part_files.append(silence_file)
            current_time += gap

        # 2. Check duration of segment audio and adjust if severely overrunning into next segment
        raw_dur = get_media_duration(seg_audio)
        work_audio = seg_audio

        # Check if next segment exists and when it starts
        next_start = float(sorted_segments[idx + 1]["start_time"]) if idx + 1 < len(sorted_segments) else total_duration
        max_allowed_dur = max(slot_dur, next_start - current_time)

        if raw_dur > max_allowed_dur * 1.15 and max_allowed_dur > 0.2:
            speed_factor = min(1.35, raw_dur / max_allowed_dur)
            speed_file = str(TEMP_DIR / f"spd_{Path(output_path).stem}_{idx}.wav")
            try:
                adjust_audio_speed(seg_audio, speed_file, speed_factor)
                if os.path.exists(speed_file) and os.path.getsize(speed_file) > 100:
                    work_audio = speed_file
                    # speed_file is an intermediate file; only the normalized version is appended below
            except Exception:
                pass

        # 3. Convert segment audio to normalized 24kHz mono WAV
        norm_file = str(TEMP_DIR / f"norm_{Path(output_path).stem}_{idx}.wav")
        cmd_norm = [
            "-i", work_audio,
            "-ar", "24000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-y", norm_file
        ]
        run_ffmpeg(cmd_norm)
        
        seg_dur = get_media_duration(norm_file)
        part_files.append(norm_file)
        current_time += seg_dur

    # 4. If remaining duration to reach total_duration, pad with tail silence
    if total_duration > current_time + 0.03:
        tail_gap = total_duration - current_time
        tail_silence = str(TEMP_DIR / f"tail_{Path(output_path).stem}_{tail_gap:.2f}.wav")
        generate_silence(tail_gap, tail_silence)
        part_files.append(tail_silence)
        current_time += tail_gap

    # 5. Write concat list
    with open(temp_concat_txt, "w", encoding="utf-8") as f:
        for p in part_files:
            p_esc = p.replace("\\", "/")
            f.write(f"file '{p_esc}'\n")

    # 6. Concat into output file
    temp_full_wav = str(TEMP_DIR / f"raw_concat_{Path(output_path).stem}.wav")
    cmd_concat = [
        "-f", "concat",
        "-safe", "0",
        "-i", str(temp_concat_txt),
        "-c:a", "pcm_s16le",
        "-ar", "24000",
        "-ac", "1",
        "-y", temp_full_wav
    ]
    res = run_ffmpeg(cmd_concat)

    # 7. Exact duration trimming/padding to guarantee 100% video-audio sync
    if os.path.exists(temp_full_wav) and os.path.getsize(temp_full_wav) > 500:
        cmd_trim = [
            "-i", temp_full_wav,
            "-t", f"{total_duration:.3f}",
            "-c:a", "pcm_s16le",
            "-y", output_path
        ]
        run_ffmpeg(cmd_trim)
        try:
            os.remove(temp_full_wav)
        except Exception:
            pass
    else:
        raise RuntimeError(f"FFmpeg audio concatenation failed:\n{res.stderr}")

    # 8. Cleanup temp parts
    try:
        if os.path.exists(temp_concat_txt):
            os.remove(temp_concat_txt)
        for p in part_files:
            if os.path.exists(p) and ("norm_" in p or "sil_" in p or "tail_" in p or "spd_" in p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass

    # 9. Verify finalized assembled track
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError("Assembled dubbed audio file is missing or empty.")

    is_audible, audit_msg = check_audio_audibility(output_path)
    if not is_audible:
        raise RuntimeError(f"Assembled dubbed audio track failed audibility check: {audit_msg}")

    return output_path



import os
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import edge_tts

import time
from config import AUDIO_DIR, TEMP_DIR, SUPPORTED_LANGUAGES
from services.audio_service import get_media_duration, adjust_audio_speed, run_ffmpeg, check_audio_audibility

from languages import (
    get_available_voices,
    get_default_voice_for_language,
    validate_voice_for_language,
    normalize_language_code,
    get_language,
    LANGUAGE_REGISTRY
)

async def synthesize_speech_async(text: str, voice: str, output_path: str, rate_factor: float = 1.0) -> str:
    """Generate speech using edge-tts with rate control, isolated temp files, retries, and audio validation."""
    clean_text = text.strip() if text else ""
    if not clean_text:
        raise ValueError("Cannot synthesize speech: text is empty.")

    # Convert rate factor (e.g. 1.0 -> "+0%", 1.2 -> "+20%", 0.8 -> "-20%")
    rate_percent = int((rate_factor - 1.0) * 100)
    rate_str = f"{rate_percent:+d}%"

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    nonce = f"{os.getpid()}_{time.time_ns()}"
    temp_mp3 = str(TEMP_DIR / f"tts_{nonce}.mp3")
    temp_wav = str(TEMP_DIR / f"tts_{nonce}.wav")
    last_err = None

    try:
        # Retry up to 3 attempts with slight backoff for network resilience
        for attempt in range(1, 4):
            try:
                communicate = edge_tts.Communicate(text=clean_text, voice=voice, rate=rate_str)
                await communicate.save(temp_mp3)
                if os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 100:
                    break
            except Exception as e:
                last_err = e
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)

        if not os.path.exists(temp_mp3) or os.path.getsize(temp_mp3) <= 100:
            err_msg = f"Edge-TTS synthesis failed for voice '{voice}' and text: '{clean_text[:50]}...'. Error: {last_err}"
            raise RuntimeError(err_msg)

        # Convert to standard 24kHz mono 16-bit WAV for seamless timeline audio editing
        cmd = [
            "-i", temp_mp3,
            "-ar", "24000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            "-y", temp_wav
        ]
        res = run_ffmpeg(cmd)

        if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) <= 100:
            raise RuntimeError(f"FFmpeg conversion to WAV failed: {res.stderr}")

        # Verify duration and audibility
        dur = get_media_duration(temp_wav)
        if dur <= 0.05:
            raise RuntimeError("Synthesized speech file has 0 duration.")

        is_audible, audit_msg = check_audio_audibility(temp_wav)
        if not is_audible:
            raise RuntimeError(f"Synthesized speech failed audibility check: {audit_msg}")

        # Atomic move to final output path to prevent concurrent read of partial files
        os.replace(temp_wav, output_path)
        return output_path

    finally:
        # Clean up temporary files
        for p in (temp_mp3, temp_wav):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

def is_indic_script(text: str, lang: str) -> bool:
    """Check if text contains native characters for Indic languages."""
    ranges = {
        "te": (0x0C00, 0x0C7F),  # Telugu
        "hi": (0x0900, 0x097F),  # Devanagari (Hindi)
        "ta": (0x0B80, 0x0BFF),  # Tamil
        "kn": (0x0C80, 0x0CFF),  # Kannada
        "ml": (0x0D00, 0x0D7F),  # Malayalam
    }
    r = ranges.get(lang.lower())
    if not r:
        return False
    return any(r[0] <= ord(c) <= r[1] for c in text)


def generate_segment_audio(
    text: str,
    target_language: str,
    project_id: str,
    segment_id: str,
    voice_name: Optional[str] = None,
    speech_rate: float = 1.0,
    slot_duration: Optional[float] = None,
    original_text: Optional[str] = None,
    source_language: Optional[str] = None
) -> Tuple[str, float, bool]:
    """
    Generate audio for a single segment from its translated text.
    Strictly verifies translation is valid and non-placeholder.
    Returns (audio_path, duration, is_timing_mismatch).
    """
    clean_text = text.strip() if text else ""
    if not clean_text:
        raise ValueError(f"Cannot synthesize speech for segment {segment_id}: translated text is empty.")

    # Reject placeholders
    if "demonstration of the imported" in clean_text.lower():
        raise ValueError(f"Segment {segment_id} contains placeholder transcript text. Genuine translation required.")

    tgt_norm = normalize_language_code(target_language)
    src_norm = normalize_language_code(source_language) if source_language else "en"

    # Reject non-translated text when target language differs from source language
    if original_text and tgt_norm != src_norm:
        clean_orig = original_text.strip().lower()
        # Indic languages must use native writing systems
        if tgt_norm in ["te", "hi", "ta", "kn", "ml"]:
            has_letters = any(c.isalpha() for c in original_text)
            if has_letters and not is_indic_script(clean_text, tgt_norm):
                if clean_text.lower() == clean_orig:
                    lang_name = get_language(tgt_norm).get("name", tgt_norm.upper())
                    raise ValueError(
                        f"Segment {segment_id} has untranslated English text ('{clean_text[:40]}...'). "
                        f"Valid {lang_name} translation required before synthesizing speech."
                    )
        elif tgt_norm in ["es", "fr", "de"]:
            # European languages: flag if identical multi-word sentence
            if len(clean_text) > 25 and clean_text.lower() == clean_orig:
                lang_name = get_language(tgt_norm).get("name", tgt_norm.upper())
                raise ValueError(
                    f"Segment {segment_id} has untranslated text identical to original ('{clean_text[:40]}...'). "
                    f"Please ensure it is genuinely translated to {lang_name}."
                )

    # Strictly validate voice against target language
    is_valid, resolved_voice, v_msg = validate_voice_for_language(tgt_norm, voice_name)
    voice_name = resolved_voice

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_file = str(AUDIO_DIR / f"voice_{project_id}_{segment_id}.wav")
    
    # Run async synthesis synchronously
    asyncio.run(synthesize_speech_async(clean_text, voice_name, out_file, speech_rate))
    
    actual_duration = get_media_duration(out_file)
    is_mismatch = False

    # Timing alignment check with slot
    if slot_duration and slot_duration > 0.1:
        if actual_duration > slot_duration * 1.15:
            is_mismatch = True
            # Attempt gentle speed-up if mismatch is moderate (up to 1.35x)
            auto_factor = min(1.35, actual_duration / slot_duration)
            if auto_factor > 1.05:
                speed_adjusted = str(TEMP_DIR / f"spd_{project_id}_{segment_id}_{time.time_ns()}.wav")
                try:
                    adjust_audio_speed(out_file, speed_adjusted, auto_factor)
                    if os.path.exists(speed_adjusted) and os.path.getsize(speed_adjusted) > 100:
                        os.replace(speed_adjusted, out_file)
                        actual_duration = get_media_duration(out_file)
                        if actual_duration <= slot_duration * 1.12:
                            is_mismatch = False
                except Exception as e:
                    print(f"Speed adjustment notice: {e}")
                finally:
                    if os.path.exists(speed_adjusted):
                        try:
                            os.remove(speed_adjusted)
                        except Exception:
                            pass

    return out_file, round(actual_duration, 2), is_mismatch


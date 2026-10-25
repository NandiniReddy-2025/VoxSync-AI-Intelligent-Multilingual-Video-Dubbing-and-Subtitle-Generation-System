import os
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

from config import TEMP_DIR, OPENAI_API_KEY
from services.audio_service import get_media_duration, check_audio_audibility, run_ffmpeg

_MODEL_CACHE: Dict[str, WhisperModel] = {}

def get_whisper_model(model_size: str = "base") -> WhisperModel:
    """
    Get or load a cached faster-whisper model.
    Downloads to local directory without symlinks to prevent Windows WinError 1314 privilege issues.
    """
    global _MODEL_CACHE
    if model_size in _MODEL_CACHE:
        return _MODEL_CACHE[model_size]

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        models_root = Path(local_appdata) / "VoxSyncAI" / "models"
    else:
        models_root = TEMP_DIR / "models"

    model_dir = models_root / f"whisper-{model_size}"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Check if model binary exists
    model_bin = model_dir / "model.bin"
    if not model_bin.exists():
        repo_id = f"Systran/faster-whisper-{model_size}"
        print(f"Downloading model {repo_id} to {model_dir}...")
        snapshot_download(repo_id, local_dir=str(model_dir))

    print(f"Loading faster-whisper model '{model_size}' from {model_dir} (CPU INT8)...")
    threads = max(1, os.cpu_count() or 4)
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=threads)
    _MODEL_CACHE[model_size] = model
    return model


def merge_coherent_segments(
    raw_segments: List[Dict[str, Any]], 
    max_duration: float = 12.0, 
    min_duration: float = 2.0,
    total_duration: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Post-process speech recognition segments to merge incomplete fragments and word boundaries
    into coherent, manageable sentences and phrases.
    """
    merged = []
    current = None

    for seg in raw_segments:
        text = seg["original_text"].strip()
        if not text:
            continue

        start = max(0.0, float(seg["start_time"]))
        end = float(seg["end_time"])
        if total_duration and total_duration > 0:
            end = min(total_duration, end)
        if end <= start:
            continue

        seg_clean = {
            "start_time": round(start, 2),
            "end_time": round(end, 2),
            "original_text": text
        }

        if current is None:
            current = dict(seg_clean)
            continue

        cur_dur = current["end_time"] - current["start_time"]
        seg_dur = seg_clean["end_time"] - seg_clean["start_time"]
        combined_dur = seg_clean["end_time"] - current["start_time"]

        ends_with_terminal = bool(re.search(r'[.!?।:]["\'\)]*$', current["original_text"]))
        starts_with_lowercase = bool(re.match(r'^[a-z]', text))
        is_continuation = starts_with_lowercase or not ends_with_terminal

        should_merge = (
            combined_dur <= max_duration and (
                is_continuation or 
                cur_dur < min_duration or 
                seg_dur < min_duration
            )
        )

        if should_merge:
            current["end_time"] = seg_clean["end_time"]
            current["original_text"] = current["original_text"].rstrip() + " " + text
        else:
            merged.append(current)
            current = dict(seg_clean)

    if current:
        merged.append(current)

    # Re-index segments and validate monotonic timestamps
    final_segments = []
    for idx, s in enumerate(merged):
        s["segment_index"] = idx
        final_segments.append(s)

    return final_segments


def transcribe_with_faster_whisper(
    audio_path: str,
    source_lang: Optional[str] = "auto",
    model_size: str = "base"
) -> Dict[str, Any]:
    """
    Transcribe speech using local faster-whisper with VAD and coherent sentence segmentation.
    Supports automatic language detection and manual language override.
    NEVER automatically translates transcript to English; preserves the original spoken language.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    total_duration = get_media_duration(audio_path)
    if total_duration <= 0.1:
        raise ValueError("Audio duration is 0 seconds. Cannot transcribe empty audio track.")

    is_audible, audit_msg = check_audio_audibility(audio_path)
    if not is_audible:
        raise ValueError(audit_msg)

    model = get_whisper_model(model_size)

    # Language handling
    lang_param = None
    if source_lang and source_lang.lower() not in ["auto", "detect", ""]:
        lang_param = source_lang.lower().split("-")[0]

    segments_iter, info = model.transcribe(
        audio_path,
        language=lang_param,
        task="transcribe", # Keep strictly "transcribe" to preserve original spoken language
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400)
    )

    raw_segments = []
    for s in segments_iter:
        txt = s.text.strip()
        if txt:
            raw_segments.append({
                "start_time": s.start,
                "end_time": s.end,
                "original_text": txt
            })

    if not raw_segments:
        raise ValueError("No recognizable speech was detected in this audio. Please check audio volume or selected language.")

    coherent_segments = merge_coherent_segments(
        raw_segments=raw_segments,
        max_duration=12.0,
        min_duration=2.0,
        total_duration=total_duration
    )

    detected_lang = info.language if info else (lang_param or "en")
    lang_prob = float(info.language_probability) if info and hasattr(info, "language_probability") else 1.0

    return {
        "segments": coherent_segments,
        "detected_language": detected_lang,
        "language_confidence": round(lang_prob, 2),
        "model_used": f"faster-whisper-{model_size} (local CPU INT8)"
    }


def retranscribe_segment_audio(
    audio_path: str,
    start_time: float,
    end_time: float,
    source_lang: Optional[str] = None
) -> str:
    """
    Retranscribe an isolated audio window for single segment retry.
    """
    model = get_whisper_model("base")
    duration = max(0.2, end_time - start_time)
    
    slice_path = str(TEMP_DIR / f"retry_{start_time:.2f}_{end_time:.2f}.wav")
    cmd = [
        "-ss", str(max(0.0, start_time - 0.1)),
        "-t", str(duration + 0.2),
        "-i", audio_path,
        "-ar", "16000",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-y", slice_path
    ]
    run_ffmpeg(cmd)

    if not os.path.exists(slice_path):
        return ""

    try:
        lang_param = source_lang.lower().split("-")[0] if source_lang and source_lang != "auto" else None
        segments_iter, _ = model.transcribe(
            slice_path,
            language=lang_param,
            task="transcribe",
            beam_size=5
        )
        texts = [s.text.strip() for s in segments_iter if s.text.strip()]
        return " ".join(texts)
    finally:
        if os.path.exists(slice_path):
            try:
                os.remove(slice_path)
            except Exception:
                pass


def transcribe_video_speech(
    audio_path: str, 
    source_lang: str = "auto",
    model_size: str = "base"
) -> Dict[str, Any]:
    """
    Main transcription entrypoint called by router.
    Uses faster-whisper locally; falls back to OpenAI Whisper API if configured and local fails.
    """
    try:
        return transcribe_with_faster_whisper(
            audio_path=audio_path,
            source_lang=source_lang,
            model_size=model_size
        )
    except Exception as e:
        print(f"faster-whisper transcription encountered: {e}")
        # If OpenAI Whisper API key is available, attempt as cloud fallback
        if OPENAI_API_KEY:
            try:
                print("Attempting OpenAI Whisper API fallback...")
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_API_KEY)
                lang = source_lang if source_lang not in ["auto", "detect", ""] else None
                with open(audio_path, "rb") as af:
                    resp = client.audio.transcriptions.create(
                        file=af,
                        model="whisper-1",
                        language=lang,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"]
                    )
                raw_segs = []
                for s in getattr(resp, "segments", []):
                    sd = s if isinstance(s, dict) else s.__dict__
                    if sd.get("text", "").strip():
                        raw_segs.append({
                            "start_time": float(sd.get("start", 0.0)),
                            "end_time": float(sd.get("end", 0.0)),
                            "original_text": sd["text"].strip()
                        })
                merged = merge_coherent_segments(raw_segs)
                return {
                    "segments": merged,
                    "detected_language": getattr(resp, "language", source_lang or "en"),
                    "language_confidence": 0.95,
                    "model_used": "OpenAI Whisper-1 API"
                }
            except Exception as oe:
                print(f"OpenAI fallback also failed: {oe}")
        raise e

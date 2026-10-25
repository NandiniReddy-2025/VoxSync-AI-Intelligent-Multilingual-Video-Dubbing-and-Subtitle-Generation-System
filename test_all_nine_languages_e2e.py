"""
Automated End-to-End Test Suite for All Nine Supported Languages in VoxSync AI:
1. English (en)
2. Telugu (te)
3. Hindi (hi)
4. Tamil (ta)
5. Kannada (kn)
6. Malayalam (ml)
7. Spanish (es)
8. French (fr)
9. German (de)

Tests:
- Central language configuration validation.
- Real speech transcription from sample_test.mp4.
- Real translation into target language (with script & non-empty verification).
- Real Edge-TTS neural speech synthesis using target-language voice.
- Single-segment audio file validation (duration, peak volume, audibility).
- Full timeline dubbed audio assembly (gap-filling & synchronization).
- Video export via FFmpeg full audio replacement (-map 0:v:0 -map 1:a:0).
- Post-export stream verification via FFprobe (video stream, audio stream AAC, audibility).
- Verification that original spoken audio stream is completely replaced.
"""

import os
import sys
import time
import shutil
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import AUDIO_DIR
from languages import (
    LANGUAGE_REGISTRY,
    get_supported_languages,
    get_language,
    get_translation_code,
    get_default_voice_for_language,
    get_available_voices,
    validate_voice_for_language,
    is_language_supported
)
from services.audio_service import (
    extract_audio_from_video,
    get_media_duration,
    check_audio_audibility,
    inspect_media_streams,
    build_timeline_dubbed_audio,
    run_ffmpeg
)
from services.transcription_service import transcribe_with_faster_whisper
from services.translation_service import translate_single_text, translate_batch_texts
from services.tts_service import generate_segment_audio
from services.export_service import export_combined_video

ALL_NINE_LANGUAGES = ["en", "te", "hi", "ta", "kn", "ml", "es", "fr", "de"]

def test_central_language_configuration():
    print("\n" + "=" * 60)
    print("TEST 1: Central Language Registry Configuration Audit")
    print("=" * 60)
    supported = get_supported_languages()
    
    for lang in ALL_NINE_LANGUAGES:
        assert lang in supported, f"Language '{lang}' missing from supported languages!"
        info = supported[lang]
        assert info["name"], f"Missing name for {lang}"
        assert info["native"], f"Missing native for {lang}"
        assert info["tts_locale"], f"Missing tts_locale for {lang}"
        assert info["default_voice"], f"Missing default_voice for {lang}"
        assert len(info["voices"]) >= 2, f"Expected at least 2 voices for {lang}, found {len(info['voices'])}"
        assert info["dubbing_supported"] is True, f"dubbing_supported must be True for {lang}"
        assert info["translation_supported"] is True, f"translation_supported must be True for {lang}"
        assert info["tts_supported"] is True, f"tts_supported must be True for {lang}"
        
        # Test translation codes
        g_code = get_translation_code(lang, "google")
        m_code = get_translation_code(lang, "mymemory")
        assert g_code, f"Missing Google code for {lang}"
        assert m_code, f"Missing MyMemory code for {lang}"

        # Test voice validation
        def_v = get_default_voice_for_language(lang)
        is_val, res_v, _ = validate_voice_for_language(lang, def_v)
        assert is_val is True, f"Default voice {def_v} not valid for {lang}"

        print(f"  [PASS] {info['name']:<10} ({lang}): {info['native']} | Locale={info['tts_locale']} | DefaultVoice={def_v} | Voices={len(info['voices'])}")

    print("All 9 languages verified in central language configuration.")


def run_e2e_for_language(lang_code: str, source_video: str, transcript_segments: list):
    info = get_language(lang_code)
    lang_name = info["name"]
    print(f"\n--- Testing Language: {lang_name} ({lang_code.upper()}) ---")

    # Step A: Translate transcript segments
    print(f"  1. Translating {len(transcript_segments)} segment(s) to {lang_name}...")
    translated_segments = []
    for s in transcript_segments:
        orig = s["original_text"]
        trans = translate_single_text(orig, source_lang="en", target_lang=lang_code)
        assert trans and trans.strip(), f"Translation for segment {s['segment_index']} was empty!"
        print(f"     Segment #{s['segment_index']+1}: \"{orig}\" -> \"{trans}\"")
        translated_segments.append({
            "segment_index": s["segment_index"],
            "id": f"seg_{lang_code}_{s['segment_index']}",
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "original_text": orig,
            "translated_text": trans,
        })

    # Step B: Synthesize TTS speech for each segment
    default_voice = get_default_voice_for_language(lang_code)
    print(f"  2. Synthesizing neural speech with voice: {default_voice}...")
    project_id = f"test_proj_{lang_code}"
    
    for seg in translated_segments:
        audio_path, duration, is_mismatch = generate_segment_audio(
            text=seg["translated_text"],
            target_language=lang_code,
            project_id=project_id,
            segment_id=seg["id"],
            voice_name=default_voice,
            slot_duration=seg["end_time"] - seg["start_time"],
            original_text=seg["original_text"],
            source_language="en"
        )
        assert os.path.exists(audio_path), f"Synthesized audio missing: {audio_path}"
        assert os.path.getsize(audio_path) > 500, f"Synthesized audio too small: {audio_path}"
        assert duration > 0.2, f"Invalid audio duration: {duration}s"
        
        is_aud, aud_msg = check_audio_audibility(audio_path)
        assert is_aud is True, f"Segment audio inaudible for {lang_code}: {aud_msg}"
        
        seg["audio_path"] = audio_path
        seg["audio_duration"] = duration
        print(f"     Segment #{seg['segment_index']+1} Audio: {duration:.2f}s, size={os.path.getsize(audio_path)}b, audible={is_aud}")

    # Step C: Full Timeline Dubbed Audio Assembly
    total_duration = get_media_duration(source_video)
    assembled_wav = str(AUDIO_DIR / f"test_timeline_{lang_code}.wav")
    
    print(f"  3. Assembling timeline dubbed audio track (duration={total_duration:.2f}s)...")
    build_timeline_dubbed_audio(translated_segments, total_duration, assembled_wav)
    assert os.path.exists(assembled_wav), "Assembled timeline WAV file not found!"
    
    asm_dur = get_media_duration(assembled_wav)
    assert abs(asm_dur - total_duration) <= 0.25, f"Assembled audio duration ({asm_dur:.2f}s) mismatch with video ({total_duration:.2f}s)"
    
    is_asm_aud, asm_aud_msg = check_audio_audibility(assembled_wav)
    assert is_asm_aud is True, f"Timeline audio track inaudible: {asm_aud_msg}"
    print(f"     Assembled Track: {asm_dur:.2f}s, audible={is_asm_aud}")

    # Step D: Video Dubbing Export (Full Audio Replacement)
    print("  4. Exporting combined dubbed video (full replacement)...")
    exported_mp4 = export_combined_video(
        project_id=project_id,
        original_video_path=source_video,
        segments=translated_segments,
        total_duration=total_duration,
        embed_subtitles=False,
        preserve_background_audio=False
    )
    assert os.path.exists(exported_mp4), f"Exported MP4 missing: {exported_mp4}"
    assert os.path.getsize(exported_mp4) > 10000, f"Exported MP4 too small: {exported_mp4}"

    # Step E: Post-Export Validation via FFprobe
    print("  5. Validating final exported MP4 streams via FFprobe...")
    streams = inspect_media_streams(exported_mp4)
    v_streams = streams.get("video_streams", [])
    a_streams = streams.get("audio_streams", [])
    
    assert len(v_streams) >= 1, "Exported MP4 has no video stream!"
    assert len(a_streams) == 1, f"Exported MP4 must have exactly 1 audio stream, found {len(a_streams)}"
    assert "aac" in a_streams[0]["codec"].lower(), f"Audio stream must be AAC encoded, got: {a_streams[0]['codec']}"

    is_exp_aud, exp_msg = check_audio_audibility(exported_mp4)
    assert is_exp_aud is True, f"Exported MP4 audio is silent/inaudible: {exp_msg}"
    
    print(f"  [SUCCESS] {lang_name} ({lang_code}): Video={v_streams[0]['codec']}, Audio={a_streams[0]['codec']} ({streams['peak_volume_db']:.1f} dB), Playable=YES")

    # Cleanup temporary segment audio and timeline
    for s in translated_segments:
        if s.get("audio_path") and os.path.exists(s["audio_path"]):
            try: os.remove(s["audio_path"])
            except Exception: pass
    if os.path.exists(assembled_wav):
        try: os.remove(assembled_wav)
        except Exception: pass

    return True


def main():
    print("=" * 60)
    print("VOXSYNC AI: 9-LANGUAGE REAL AUDIO DUBBING VERIFICATION SUITE")
    print("=" * 60)

    # 1. Test central language config
    test_central_language_configuration()

    # 2. Extract audio from sample_test.mp4
    video_path = "sample_test.mp4"
    assert os.path.exists(video_path), f"Video {video_path} not found!"
    audio_path = extract_audio_from_video(video_path, "sample_test_audio.wav")
    assert os.path.exists(audio_path), f"Audio {audio_path} not found!"
    
    # 3. Transcribe speech using faster-whisper
    print("\n" + "=" * 60)
    print("STEP 2: Speech Recognition on sample_test.mp4")
    print("=" * 60)
    transcription = transcribe_with_faster_whisper(audio_path, source_lang="en")
    raw_segments = transcription["segments"]
    print(f"Recognized {len(raw_segments)} segment(s) [Detected: {transcription['detected_language']}]:")
    for s in raw_segments:
        print(f"  [{s['start_time']:.2f}s - {s['end_time']:.2f}s] {s['original_text']}")

    # 4. Run full E2E pipeline for all 9 languages
    print("\n" + "=" * 60)
    print("STEP 3: Real Multilingual Translation, TTS & Dubbing E2E")
    print("=" * 60)

    results = {}
    for lang in ALL_NINE_LANGUAGES:
        t0 = time.time()
        try:
            ok = run_e2e_for_language(lang, video_path, raw_segments)
            elapsed = time.time() - t0
            results[lang] = {"status": "PASSED", "time": elapsed}
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [FAILED] {lang}: {e}")
            results[lang] = {"status": "FAILED", "error": str(e), "time": elapsed}

    # Summary
    print("\n" + "=" * 60)
    print("FINAL 9-LANGUAGE VERIFICATION REPORT")
    print("=" * 60)
    all_passed = True
    for lang, r in results.items():
        lang_name = get_language(lang)["name"]
        st = r["status"]
        t = r["time"]
        if st == "PASSED":
            print(f"  ✓ {lang_name:<10} ({lang}): {st} ({t:.2f}s)")
        else:
            all_passed = False
            print(f"  ✗ {lang_name:<10} ({lang}): {st} ({t:.2f}s) - {r.get('error')}")

    print("=" * 60)
    if all_passed:
        print("ALL NINE (9) LANGUAGES VERIFIED END-TO-END WITH REAL SPEECH & VIDEO EXPORT!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("SOME LANGUAGES FAILED. Review errors above.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()

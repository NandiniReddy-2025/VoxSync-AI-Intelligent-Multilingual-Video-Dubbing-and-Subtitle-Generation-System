import os
import sys
import re
import requests
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8010/api"

def get_auth_headers():
    reg_payload = {
        "email": "audio_engineer@voxsync.ai",
        "password": "DubbingPass2026!",
        "full_name": "Audio Engineer"
    }
    r = requests.post(f"{BASE_URL}/auth/register", json=reg_payload)
    if r.status_code == 200:
        token = r.json()["access_token"]
    else:
        login_r = requests.post(f"{BASE_URL}/auth/login", json={"email": reg_payload["email"], "password": reg_payload["password"]})
        assert login_r.status_code == 200, f"Login failed: {login_r.text}"
        token = login_r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def run_ffmpeg_probe(file_path):
    import subprocess
    from config import FFMPEG_EXE
    cmd = [FFMPEG_EXE, "-i", str(file_path), "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stderr

def run_all_tests():
    print("=" * 65)
    print("VOXSYNC AI: COMPREHENSIVE AUDIO DUBBING PIPELINE VERIFICATION")
    print("=" * 65)

    headers = get_auth_headers()
    sample_video = Path("sample_test.mp4")
    assert sample_video.exists(), "sample_test.mp4 missing from backend folder"

    # =========================================================================
    # TEST C: Multi-Segment Verification (Missing Sentences Prevention)
    # =========================================================================
    print("\n[TEST C] Testing Multi-Segment Speech Assembly & Zero-Omission Pipeline...")
    proj_res = requests.post(
        f"{BASE_URL}/projects",
        json={
            "title": "Test C: Multi-Segment Dubbing Assembly",
            "source_language": "en",
            "target_language": "te"
        },
        headers=headers
    )
    assert proj_res.status_code == 200, f"Failed to create project: {proj_res.text}"
    p_c_id = proj_res.json()["id"]

    with open(sample_video, "rb") as f:
        up_res = requests.post(
            f"{BASE_URL}/media/projects/{p_c_id}/upload",
            files={"file": ("sample_test.mp4", f, "video/mp4")},
            headers=headers
        )
    assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
    proj_c = up_res.json()
    print(f" -> Project created & video uploaded (Duration: {proj_c['duration']}s)")

    # Add 3 distinct consecutive segments
    segments_to_add = [
        {"segment_index": 0, "start_time": 0.0, "end_time": 1.4, "original_text": "Hello, welcome to VoxSync AI.", "translated_text": "నమస్కారం, VoxSync AI కి స్వాగతం."},
        {"segment_index": 1, "start_time": 1.6, "end_time": 3.2, "original_text": "We are generating intelligent video dubbing.", "translated_text": "మేము ఇంటెలిజెంట్ వీడియో డబ్బింగ్‌ను రూపొందిస్తున్నాము."},
        {"segment_index": 2, "start_time": 3.4, "end_time": 4.8, "original_text": "Every sentence is accurately synchronized.", "translated_text": "ప్రతి వాక్యం ఖచ్చితంగా సమకాలీకరించబడింది."}
    ]

    for s in segments_to_add:
        r = requests.post(f"{BASE_URL}/projects/{p_c_id}/transcription/segments", json=s, headers=headers)
        assert r.status_code == 200, f"Add segment failed: {r.text}"

    print(f" -> Added {len(segments_to_add)} distinct segments spanning total duration.")

    # Synthesize speech for all segments
    tts_res = requests.post(
        f"{BASE_URL}/projects/{p_c_id}/voiceover",
        json={"voice_name": "te-IN-ShrutiNeural", "speech_rate": 1.0},
        headers=headers
    )
    assert tts_res.status_code == 200, f"Voiceover failed: {tts_res.text}"
    dubbed_c = tts_res.json()

    # Validate each segment
    assert len(dubbed_c["segments"]) == 3, f"Expected 3 segments, got {len(dubbed_c['segments'])}"
    for idx, s in enumerate(dubbed_c["segments"]):
        assert s["status"] == "synthesized", f"Segment #{idx+1} status is {s['status']}"
        assert s["audio_path"] and os.path.exists(s["audio_path"]), f"Segment #{idx+1} audio file missing on disk"
        assert s["audio_duration"] > 0.1, f"Segment #{idx+1} duration is {s['audio_duration']}"
        print(f"    Segment #{idx+1} ({s['start_time']}s-{s['end_time']}s): Audio={os.path.basename(s['audio_path'])}, Duration={s['audio_duration']}s")

    # Check full timeline dubbed audio
    assert dubbed_c["dubbed_audio_path"] and os.path.exists(dubbed_c["dubbed_audio_path"])
    full_audio_dur = requests.get(f"{BASE_URL}/projects/{p_c_id}/dubbed-audio", headers=headers)
    assert full_audio_dur.status_code in [200, 206], "Dubbed audio streaming failed"

    # Verify Dubbing Diagnostics endpoint (PHASE 7)
    diag_res = requests.get(f"{BASE_URL}/projects/{p_c_id}/dubbing-diagnostics", headers=headers)
    assert diag_res.status_code == 200, f"Diagnostics endpoint failed: {diag_res.text}"
    diag = diag_res.json()
    assert diag["total_segments"] == 3
    assert diag["translated_segments"] == 3
    assert diag["synthesized_segments"] == 3
    assert diag["missing_segments"] == 0
    assert len(diag["failed_segment_ids"]) == 0
    assert diag["assembled_audio_ready"] == True
    assert diag["assembled_audio_audible"] == True
    print(f" -> Diagnostics: PASS (Total={diag['total_segments']}, Synthesized={diag['synthesized_segments']}/{diag['total_segments']}, Audio Ready={diag['assembled_audio_ready']}, Peak={diag['assembled_audio_peak_db']} dB)")
    print(" -> TEST C RESULT: PASS (All sentences dubbed, assembled, and accounted for without omission)")

    # =========================================================================
    # TEST A & B: Audio Replacement & Audible Master MP4 Export
    # =========================================================================
    print("\n[TEST A & B] Testing Master Video Export: Original Voice Replacement & Audible Target Audio...")
    export_res = requests.post(
        f"{BASE_URL}/projects/{p_c_id}/export",
        json={"export_type": "video_dubbed", "embed_subtitles": False, "preserve_background_audio": False},
        headers=headers
    )
    assert export_res.status_code == 200, f"Video export failed: {export_res.text}"
    job = export_res.json()
    assert job["status"] == "completed", f"Export status is {job['status']}: {job.get('error_message')}"
    out_file = job["output_path"]
    assert os.path.exists(out_file), f"Exported file {out_file} not found on disk"
    assert os.path.getsize(out_file) > 5000, f"Exported video too small ({os.path.getsize(out_file)} bytes)"
    print(f" -> Exported Master Dubbed Video: {os.path.basename(out_file)} ({os.path.getsize(out_file)} bytes)")

    # Inspect stream layout via inspect_media_streams
    from services.audio_service import inspect_media_streams
    streams_info = inspect_media_streams(out_file)

    video_streams = streams_info["video_streams"]
    audio_streams = streams_info["audio_streams"]
    peak_vol = streams_info["peak_volume_db"]

    assert len(video_streams) >= 1, "Exported MP4 has no video stream!"
    assert len(audio_streams) == 1, f"Expected exactly 1 audio stream, found {len(audio_streams)}!"
    assert audio_streams[0]["codec"].lower() == "aac", f"Audio codec should be AAC, found {audio_streams[0]['codec']}"
    print(f" -> Stream Verification: PASS (Video={video_streams[0]['codec']}, Audio={audio_streams[0]['codec']})")

    # 2. Inspect Audio Audibility (Peak Volume in dB)
    assert peak_vol is not None, "FFmpeg volumedetect failed to parse max_volume"
    print(f" -> Audio Peak Volume: {peak_vol:.1f} dB")
    assert peak_vol > -60.0, f"Exported video is SILENT! Peak volume is {peak_vol} dB (must be > -60 dB)"
    print(" -> TEST B RESULT: PASS (Exported video contains genuine, audible synthesized audio)")

    # 3. Verify Original Audio is Not Present (Test A)
    # In full replacement mode, only the visual stream [0:v:0] and dubbed stream [1:a:0] were mapped.
    # Total audio stream count is strictly 1 (AAC). Original audio was NOT copied.
    assert len(audio_streams) == 1, "Original audio was accidentally mapped alongside dubbed audio!"
    print(" -> TEST A RESULT: PASS (Original voice audio is completely excluded; only dubbed audio is present)")

    # =========================================================================
    # TEST D: Deliberate TTS Failure & Missing Segment Protection
    # =========================================================================
    print("\n[TEST D] Testing Deliberate Failure Handling & Rejection of Silent/Missing Segments...")
    proj_d_res = requests.post(
        f"{BASE_URL}/projects",
        json={"title": "Test D: Deliberate Failure", "source_language": "en", "target_language": "te"},
        headers=headers
    )
    p_d_id = proj_d_res.json()["id"]

    # Add 2 segments, 1 without translation
    requests.post(
        f"{BASE_URL}/projects/{p_d_id}/transcription/segments",
        json={"segment_index": 0, "start_time": 0.0, "end_time": 2.0, "original_text": "Testing failure.", "translated_text": "పరీక్ష విఫలమైంది."},
        headers=headers
    )
    requests.post(
        f"{BASE_URL}/projects/{p_d_id}/transcription/segments",
        json={"segment_index": 1, "start_time": 2.2, "end_time": 4.5, "original_text": "Missing translation.", "translated_text": ""},
        headers=headers
    )

    # Attempt voiceover when 1 translation is missing
    bad_voice_res = requests.post(
        f"{BASE_URL}/projects/{p_d_id}/voiceover",
        json={"voice_name": "te-IN-ShrutiNeural"},
        headers=headers
    )
    assert bad_voice_res.status_code == 400, f"Expected 400 rejection for missing translation, got {bad_voice_res.status_code}"
    print(f" -> Missing translation rejection: PASS ('{bad_voice_res.json()['detail'][:60]}...')")

    # Attempt export when audio is not generated
    bad_export_res = requests.post(
        f"{BASE_URL}/projects/{p_d_id}/export",
        json={"export_type": "video_dubbed"},
        headers=headers
    )
    assert bad_export_res.status_code in [400, 422], f"Expected 400/422 for missing audio export, got {bad_export_res.status_code}"
    print(f" -> Missing audio export rejection: PASS ('{bad_export_res.json()['detail'][:60]}...')")
    print(" -> TEST D RESULT: PASS (Application refuses to silently omit or export incomplete dubs)")

    print("\n" + "=" * 65)
    print("ALL TESTS (TEST A, TEST B, TEST C, TEST D) PASSED PERFECTLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_all_tests()

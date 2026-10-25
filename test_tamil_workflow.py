"""
Test Complete Tamil Dubbing Workflow End-to-End
Verifies:
1. Project creation with target language = 'ta' (Tamil)
2. Translation requests reach backend and store genuine Tamil text
3. Retranslate single segment into Tamil
4. Voice synthesis with Tamil neural voice (ta-IN-ValluvarNeural & ta-IN-PallaviNeural)
5. Retry audio for a segment
6. Dubbed audio timeline assembly
7. Final video export with dubbed audio in Tamil
8. Dubbing diagnostics report
"""

import sys
import os
import json
import requests
import subprocess
from pathlib import Path

# Ensure UTF-8 output for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8010/api"

def get_auth_token():
    reg_url = f"{BASE_URL}/auth/register"
    reg_data = {"email": "test_tamil@voxsync.ai", "password": "Password123!", "full_name": "Tamil Test User"}
    resp = requests.post(reg_url, json=reg_data)
    if resp.status_code == 200:
        return resp.json()["access_token"]
    
    login_url = f"{BASE_URL}/auth/login"
    login_data = {"email": "test_tamil@voxsync.ai", "password": "Password123!"}
    resp = requests.post(login_url, json=login_data)
    if resp.status_code == 200:
        return resp.json()["access_token"]
    raise RuntimeError(f"Auth failed: {resp.text}")

def run_tamil_workflow():
    print("=" * 60)
    print("STARTING COMPLETE TAMIL DUBBING WORKFLOW TEST")
    print("=" * 60)

    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1. Create project with Tamil target
    print("\n[STEP 1] Creating project with target_language = 'ta'...")
    proj_resp = requests.post(
        f"{BASE_URL}/projects",
        headers=headers,
        json={"title": "Tamil Dubbing Test Project", "source_language": "en", "target_language": "ta"}
    )
    assert proj_resp.status_code == 200, f"Create project failed: {proj_resp.text}"
    project = proj_resp.json()
    project_id = project["id"]
    print(f"Project created: ID={project_id}, source={project['source_language']}, target={project['target_language']}")
    assert project["target_language"] == "ta"

    # 2. Upload sample video
    print("\n[STEP 2] Uploading sample test video...")
    sample_video = Path("sample_test.mp4")
    assert sample_video.exists(), "sample_test.mp4 not found"
    
    with open(sample_video, "rb") as f:
        upload_resp = requests.post(
            f"{BASE_URL}/media/projects/{project_id}/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("sample_test.mp4", f, "video/mp4")}
        )
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    print("Video uploaded successfully. Duration:", upload_resp.json().get("duration"))

    # 3. Add transcript segments
    print("\n[STEP 3] Adding transcript segments...")
    test_segments = [
        {"segment_index": 0, "start_time": 0.0, "end_time": 2.2, "original_text": "Welcome to our video dubbing system."},
        {"segment_index": 1, "start_time": 2.4, "end_time": 4.2, "original_text": "We support multiple Indian languages including Tamil."},
        {"segment_index": 2, "start_time": 4.4, "end_time": 5.0, "original_text": "Thank you for watching."}
    ]
    created_segments = []
    for s in test_segments:
        seg_resp = requests.post(
            f"{BASE_URL}/projects/{project_id}/transcription/segments",
            headers=headers,
            json=s
        )
        assert seg_resp.status_code == 200, f"Add segment failed: {seg_resp.text}"
        created_segments.append(seg_resp.json())
    print(f"Added {len(created_segments)} segments.")

    # 4. Trigger Translation to Tamil
    print("\n[STEP 4] Translating all segments to Tamil ('ta')...")
    trans_resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/translation",
        headers=headers,
        json={"target_language": "ta"}
    )
    assert trans_resp.status_code == 200, f"Translation failed: {trans_resp.text}"
    trans_project = trans_resp.json()
    trans_segs = trans_project.get("segments", [])
    assert len(trans_segs) == 3, f"Expected 3 segments, got {len(trans_segs)}"

    for idx, seg in enumerate(trans_segs):
        t_text = seg.get("translated_text", "")
        print(f"  Segment #{idx + 1}:")
        print(f"    Original:   {seg.get('original_text')}")
        print(f"    Tamil:      {repr(t_text)}")
        assert t_text and len(t_text.strip()) > 0, f"Segment #{idx + 1} has empty Tamil translation!"
        assert t_text != seg.get("original_text"), f"Segment #{idx + 1} translation fell back to original text!"

    # 5. Retranslate single segment in Tamil
    print("\n[STEP 5] Retranslating segment #1 in Tamil...")
    seg0_id = trans_segs[0]["id"]
    retrans_resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/translation/segments/{seg0_id}/retranslate",
        headers=headers,
        json={"target_language": "ta", "original_text": "Welcome to our video dubbing system."}
    )
    assert retrans_resp.status_code == 200, f"Retranslate failed: {retrans_resp.text}"
    seg0_updated = retrans_resp.json()
    print("  Retranslated text:", repr(seg0_updated.get("translated_text")))
    assert seg0_updated.get("translated_text"), "Retranslated text is empty"

    # 6. Generate Tamil voiceovers (ta-IN-ValluvarNeural)
    print("\n[STEP 6] Synthesizing speech with Tamil neural voice 'ta-IN-ValluvarNeural'...")
    tts_resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/voiceover",
        headers=headers,
        json={"voice_name": "ta-IN-ValluvarNeural", "speech_rate": 1.0}
    )
    assert tts_resp.status_code == 200, f"Voiceover generation failed: {tts_resp.text}"
    tts_project = tts_resp.json()
    tts_segs = tts_project.get("segments", [])

    for idx, s in enumerate(tts_segs):
        audio_path = s.get("audio_path")
        dur = s.get("audio_duration", 0)
        print(f"  Segment #{idx + 1} Tamil audio: {audio_path} (duration: {dur:.2f}s)")
        assert audio_path and os.path.exists(audio_path), f"Audio file missing for segment #{idx + 1}"
        assert dur > 0.1, f"Audio duration too short for segment #{idx + 1}: {dur}s"
        assert os.path.getsize(audio_path) > 1000, f"Audio file unexpectedly tiny: {os.path.getsize(audio_path)} bytes"

    # 7. Retry Audio for Segment #2 with 'ta-IN-PallaviNeural'
    print("\n[STEP 7] Retrying audio for segment #2 with 'ta-IN-PallaviNeural'...")
    seg1_id = tts_segs[1]["id"]
    retry_audio_resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/segments/{seg1_id}/audio",
        headers=headers,
        json={"voice_name": "ta-IN-PallaviNeural", "speech_rate": 1.0}
    )
    assert retry_audio_resp.status_code == 200, f"Retry audio failed: {retry_audio_resp.text}"
    seg1_updated = retry_audio_resp.json()
    print(f"  Segment #2 regenerated: {seg1_updated.get('audio_path')} (dur: {seg1_updated.get('audio_duration'):.2f}s)")
    assert seg1_updated.get("audio_path") and os.path.exists(seg1_updated.get("audio_path"))

    # 8. Check Dubbed Audio Track
    print("\n[STEP 8] Checking assembled Tamil dubbed audio track...")
    audio_resp = requests.get(f"{BASE_URL}/projects/{project_id}/dubbed-audio", headers=headers)
    assert audio_resp.status_code in (200, 206), f"Dubbed audio stream failed: {audio_resp.status_code}"
    print(f"Assembled audio stream returned HTTP {audio_resp.status_code}, content length = {len(audio_resp.content)} bytes")
    assert len(audio_resp.content) > 10000, "Dubbed audio stream is too small!"

    # 9. Export Dubbed Video in Tamil
    print("\n[STEP 9] Exporting final dubbed video in Tamil...")
    export_resp = requests.post(
        f"{BASE_URL}/projects/{project_id}/export",
        headers=headers,
        json={
            "export_type": "video_dubbed",
            "embed_subtitles": False,
            "subtitle_mode": "translated",
            "preserve_background_audio": False
        }
    )
    assert export_resp.status_code == 200, f"Export failed: {export_resp.text}"
    export_job = export_resp.json()
    export_path = export_job.get("output_path")
    print(f"Export Job ID={export_job['id']}, status={export_job['status']}, output={export_path}")
    assert export_job["status"] == "completed", f"Export job status is {export_job['status']}"
    assert export_path and os.path.exists(export_path), f"Export output file does not exist: {export_path}"
    file_size = os.path.getsize(export_path)
    print(f"Exported video file size: {file_size} bytes")
    assert file_size > 50000, f"Exported file is unexpectedly small: {file_size} bytes"

    # 10. Check Dubbing Diagnostics
    print("\n[STEP 10] Checking dubbing diagnostics...")
    diag_resp = requests.get(f"{BASE_URL}/projects/{project_id}/dubbing-diagnostics", headers=headers)
    assert diag_resp.status_code == 200, f"Diagnostics failed: {diag_resp.text}"
    diag = diag_resp.json()
    print("  Diagnostics summary:")
    print(f"    Target Language:         {diag['target_language']}")
    print(f"    Total Segments:          {diag['total_segments']}")
    print(f"    Translated Segments:     {diag['translated_segments']}")
    print(f"    Synthesized Segments:    {diag['synthesized_segments']}")
    print(f"    Missing Segments:        {diag['missing_segments']}")
    print(f"    Assembled Audio Audible: {diag['assembled_audio_audible']}")
    print(f"    Video Streams:           {diag['video_stream_count']}")
    print(f"    Audio Streams:           {diag['audio_stream_count']}")
    print(f"    Audio Codec:             {diag['audio_codec']}")
    print(f"    Export Status:           {diag['export_status']}")

    assert diag["target_language"] == "ta"
    assert diag["total_segments"] == 3
    assert diag["translated_segments"] == 3
    assert diag["synthesized_segments"] == 3
    assert diag["missing_segments"] == 0
    assert diag["assembled_audio_audible"] is True
    assert diag["audio_stream_count"] == 1
    assert diag["video_stream_count"] == 1
    assert diag["export_status"] in ("completed", "export_completed")

    print("\n" + "=" * 60)
    print("TAMIL DUBBING PIPELINE FULLY VERIFIED - ALL 10 TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        run_tamil_workflow()
    except Exception as e:
        print("\nTEST FAILED WITH EXCEPTION:", repr(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)

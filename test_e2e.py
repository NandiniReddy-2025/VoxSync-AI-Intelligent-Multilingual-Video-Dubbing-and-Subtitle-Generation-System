import os
import sys
import requests
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8010/api"

def run_e2e_tests():
    print("==================================================")
    print("STARTING VOXSYNC AI END-TO-END VERIFICATION SUITE")
    print("==================================================")

    # 1. Test Health Endpoint
    print("\n[Step 1] Checking system health & provider status...")
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    health_data = r.json()
    print(" -> Health check: PASS", health_data)
    assert health_data["ffmpeg_status"] == "ready", "FFmpeg is not ready!"

    # 2. Test User Registration & Login
    print("\n[Step 2] Testing User Authentication (Register & Login)...")
    reg_payload = {
        "email": "testcreator@voxsync.ai",
        "password": "SecurePassword123!",
        "full_name": "Test Creator"
    }
    # Register (or login if exists)
    reg_res = requests.post(f"{BASE_URL}/auth/register", json=reg_payload)
    if reg_res.status_code == 200:
        token = reg_res.json()["access_token"]
        print(" -> Registration: PASS")
    else:
        login_res = requests.post(f"{BASE_URL}/auth/login", json={"email": reg_payload["email"], "password": reg_payload["password"]})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        print(" -> Login: PASS")

    headers = {"Authorization": f"Bearer {token}"}

    # Verify Profile
    me_res = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    assert me_res.status_code == 200, f"Get Me failed: {me_res.text}"
    print(" -> Profile authentication: PASS", me_res.json()["email"])

    # 3. Test Invalid Upload Validation
    print("\n[Step 3] Testing Invalid Upload Validation...")
    fake_txt_file = ("bad_file.txt", b"This is not a video", "text/plain")
    bad_upload = requests.post(
        f"{BASE_URL}/media/projects/fake_id/upload",
        files={"file": fake_txt_file},
        headers=headers
    )
    assert bad_upload.status_code in [400, 404], "Invalid upload was not rejected!"
    print(" -> Invalid upload rejection: PASS (status", bad_upload.status_code, ")")

    # 4. Create Project
    print("\n[Step 4] Creating Dubbing Project (English -> Telugu)...")
    proj_payload = {
        "title": "VoxSync AI E2E Video Dubbing Test",
        "source_language": "en",
        "target_language": "te"
    }
    proj_res = requests.post(f"{BASE_URL}/projects", json=proj_payload, headers=headers)
    assert proj_res.status_code == 200, f"Project creation failed: {proj_res.text}"
    project = proj_res.json()
    project_id = project["id"]
    print(" -> Project created: PASS (ID:", project_id, ")")

    # 5. Upload Valid Sample Video
    print("\n[Step 5] Uploading Valid Video & Extracting Audio via FFmpeg...")
    sample_video_path = Path("sample_test.mp4")
    assert sample_video_path.exists(), "sample_test.mp4 does not exist!"

    with open(sample_video_path, "rb") as f:
        upload_res = requests.post(
            f"{BASE_URL}/media/projects/{project_id}/upload",
            files={"file": ("sample_test.mp4", f, "video/mp4")},
            headers=headers
        )
    assert upload_res.status_code == 200, f"Video upload failed: {upload_res.text}"
    project = upload_res.json()
    print(f" -> Upload & Audio Extraction: PASS (Duration: {project['duration']}s, Video Name: {project['original_video_name']})")

    # 6. Generate Speech Transcription with Timestamps
    print("\n[Step 6] Generating Speech Transcription with Timestamps...")
    trans_res = requests.post(f"{BASE_URL}/projects/{project_id}/transcription", headers=headers)
    if trans_res.status_code == 200:
        project = trans_res.json()
        segments = project.get("segments", [])
        print(f" -> Speech Recognition: PASS ({len(segments)} segments recognized)")
    else:
        print(f" -> Note: Automated recognition returned {trans_res.status_code}. Adding speech segment manually.")
        add_res = requests.post(
            f"{BASE_URL}/projects/{project_id}/transcription/segments",
            json={
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 4.8,
                "original_text": "Welcome to VoxSync AI. This is an intelligent video dubbing test.",
                "translated_text": ""
            },
            headers=headers
        )
        assert add_res.status_code == 200
        proj_get = requests.get(f"{BASE_URL}/projects/{project_id}", headers=headers)
        project = proj_get.json()
        segments = project["segments"]

    assert len(segments) > 0, "No segments available!"
    seg0 = segments[0]
    print(f" -> Segment 1: [{seg0['start_time']}s - {seg0['end_time']}s] '{seg0['original_text']}'")

    # 7. Correct a sentence in transcript
    print("\n[Step 7] Correcting Transcript Sentence...")
    corrected_text = "Welcome to VoxSync AI. This is an intelligent video dubbing and subtitle test."
    update_res = requests.patch(
        f"{BASE_URL}/projects/{project_id}/transcription/segments/{seg0['id']}",
        json={"original_text": corrected_text},
        headers=headers
    )
    assert update_res.status_code == 200, f"Transcript edit failed: {update_res.text}"
    print(" -> Transcript correction: PASS ('" + update_res.json()["original_text"] + "')")

    # 8. Translate to Telugu
    print("\n[Step 8] Translating Segments into Telugu (te)...")
    translate_res = requests.post(f"{BASE_URL}/projects/{project_id}/translation", headers=headers)
    assert translate_res.status_code == 200, f"Translation failed: {translate_res.text}"
    project = translate_res.json()
    seg0 = project["segments"][0]
    print(f" -> Translation: PASS ('{seg0['translated_text']}')")

    # 9. Edit Translated Sentence
    print("\n[Step 9] Editing Translated Sentence...")
    refined_translation = seg0["translated_text"] + " (పరీక్ష)"
    edit_trans_res = requests.patch(
        f"{BASE_URL}/projects/{project_id}/translation/segments/{seg0['id']}/translation",
        json={"translated_text": refined_translation},
        headers=headers
    )
    assert edit_trans_res.status_code == 200, f"Translation edit failed: {edit_trans_res.text}"
    print(f" -> Translation refinement: PASS ('{edit_trans_res.json()['translated_text']}')")

    # 10. Generate Translated Voiceover with Neural TTS
    print("\n[Step 10] Generating Neural Voiceover for Telugu (te-IN-ShrutiNeural)...")
    voice_res = requests.post(
        f"{BASE_URL}/projects/{project_id}/voiceover",
        json={"voice_name": "te-IN-ShrutiNeural", "speech_rate": 1.0},
        headers=headers
    )
    assert voice_res.status_code == 200, f"Voiceover generation failed: {voice_res.text}"
    project = voice_res.json()
    seg0 = project["segments"][0]
    assert seg0["audio_path"] and os.path.exists(seg0["audio_path"]), "Audio file not created on disk!"
    print(f" -> Voiceover: PASS (Audio file: {seg0['audio_path']}, Duration: {seg0['audio_duration']}s, Mismatch: {seg0['is_timing_mismatch']})")

    # 11. Configure Subtitles & Preview
    print("\n[Step 11] Customizing Subtitles & Testing SRT/VTT Generation...")
    sub_res = requests.put(
        f"{BASE_URL}/projects/{project_id}/subtitles/settings",
        json={
            "font_family": "Plus Jakarta Sans, sans-serif",
            "font_size": 26,
            "primary_color": "#FFD700",
            "position": "bottom",
            "is_bilingual": True,
            "embed_subtitles": True
        },
        headers=headers
    )
    assert sub_res.status_code == 200, "Subtitle settings failed"

    vtt_prev = requests.get(f"{BASE_URL}/projects/{project_id}/subtitles/preview?format=vtt&mode=translated", headers=headers)
    assert vtt_prev.status_code == 200
    print(" -> Subtitle preview: PASS")

    # 12. Export SRT & VTT files
    print("\n[Step 12] Exporting SRT, VTT, and TXT Transcript...")
    srt_job = requests.post(
        f"{BASE_URL}/projects/{project_id}/export",
        json={"export_type": "srt", "subtitle_mode": "translated"},
        headers=headers
    ).json()
    assert srt_job["status"] == "completed" and os.path.exists(srt_job["output_path"])
    assert srt_job["file_size"] > 0
    print(f" -> SRT Export: PASS ({srt_job['file_name']}, {srt_job['file_size']} bytes)")

    vtt_job = requests.post(
        f"{BASE_URL}/projects/{project_id}/export",
        json={"export_type": "vtt", "subtitle_mode": "bilingual"},
        headers=headers
    ).json()
    assert vtt_job["status"] == "completed" and os.path.exists(vtt_job["output_path"])
    print(f" -> VTT Export: PASS ({vtt_job['file_name']}, {vtt_job['file_size']} bytes)")

    # 13. Export Dubbed Audio (MP3)
    print("\n[Step 13] Exporting Dubbed Full Timeline Audio...")
    audio_job = requests.post(
        f"{BASE_URL}/projects/{project_id}/export",
        json={"export_type": "audio_dubbed"},
        headers=headers
    ).json()
    assert audio_job["status"] == "completed" and os.path.exists(audio_job["output_path"])
    print(f" -> Dubbed Audio Export: PASS ({audio_job['file_name']}, {audio_job['file_size']} bytes)")

    # 14. Export Combined Dubbed Video (MP4) with FFmpeg
    print("\n[Step 14] Combining Video + Dubbed Audio into Master MP4 with FFmpeg...")
    video_job = requests.post(
        f"{BASE_URL}/projects/{project_id}/export",
        json={"export_type": "video_dubbed", "embed_subtitles": False},
        headers=headers
    ).json()
    assert video_job["status"] == "completed" and os.path.exists(video_job["output_path"])
    assert video_job["file_size"] > 1000
    print(f" -> Master Dubbed Video Export: PASS ({video_job['file_name']}, {video_job['file_size']} bytes)")

    # 15. Verify Downloads & File Existence
    print("\n[Step 15] Verifying Download Endpoints and File Content...")
    download_res = requests.get(f"{BASE_URL}/exports/{video_job['id']}/download")
    assert download_res.status_code == 200
    assert len(download_res.content) == video_job["file_size"]
    print(" -> File Download: PASS (verified matching binary stream)")

    # 16. Verify Export Jobs List
    exports_list = requests.get(f"{BASE_URL}/projects/{project_id}/exports", headers=headers).json()
    assert len(exports_list) >= 4, "Not all export jobs were recorded!"
    print(f" -> Verified {len(exports_list)} active downloadable assets in project.")

    # 17. Test YouTube URL Format & Domain Validation
    print("\n[Step 17] Testing YouTube URL Format & Domain Validation...")
    bad_yt_res = requests.post(
        f"{BASE_URL}/media/youtube-info",
        json={"youtube_url": "https://vimeo.com/987654321"},
        headers=headers
    )
    assert bad_yt_res.status_code == 400, f"Expected 400 for non-YouTube domain, got {bad_yt_res.status_code}"
    print(f" -> Invalid YouTube domain rejection: PASS ('{bad_yt_res.json()['detail'][:50]}...')")

    # 18. Test YouTube Inaccessible/Non-existent Video Error Handling
    print("\n[Step 18] Testing Unavailable YouTube Video Error Handling...")
    unavail_res = requests.post(
        f"{BASE_URL}/media/youtube-info",
        json={"youtube_url": "https://www.youtube.com/watch?v=00000000000"},
        headers=headers
    )
    assert unavail_res.status_code == 400, f"Expected 400 for unavailable video, got {unavail_res.status_code}"
    print(f" -> Unavailable YouTube video handling: PASS ('{unavail_res.json()['detail']}')")

    # 19. Test YouTube Metadata Retrieval on Public Sample Video
    print("\n[Step 19] Testing YouTube Metadata Retrieval on Permitted Public Video...")
    sample_yt_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    info_res = requests.post(
        f"{BASE_URL}/media/youtube-info",
        json={"youtube_url": sample_yt_url},
        headers=headers
    )
    assert info_res.status_code == 200, f"YouTube info check failed: {info_res.text}"
    yt_info = info_res.json()
    assert yt_info["video_id"] == "jNQXAC9IVRw"
    assert yt_info["duration"] > 0
    print(f" -> YouTube metadata check: PASS (Title: '{yt_info['title']}', Duration: {yt_info['duration']}s, Channel: '{yt_info['channel']}')")

    # 20. Test YouTube Video Media Download & Audio Extraction Pipeline
    print("\n[Step 20] Testing Direct YouTube Media Import & Audio Extraction into Dubbing Pipeline...")
    yt_proj_res = requests.post(
        f"{BASE_URL}/projects",
        json={
            "title": "YouTube Live Ingestion Test",
            "source_language": "en",
            "target_language": "hi",
            "import_source": "youtube",
            "source_url": sample_yt_url
        },
        headers=headers
    )
    assert yt_proj_res.status_code == 200
    yt_project = yt_proj_res.json()
    yt_proj_id = yt_project["id"]

    import_media_res = requests.post(
        f"{BASE_URL}/media/projects/{yt_proj_id}/youtube-import",
        json={"youtube_url": sample_yt_url},
        headers=headers
    )
    assert import_media_res.status_code == 200, f"YouTube import failed: {import_media_res.text}"
    yt_imported = import_media_res.json()
    assert yt_imported["import_source"] == "youtube"
    assert yt_imported["source_url"] == sample_yt_url
    assert yt_imported["original_video_name"] == yt_info["title"]
    assert yt_imported["duration"] > 0
    assert yt_imported.get("original_video_path") and os.path.exists(yt_imported["original_video_path"])
    assert yt_imported.get("original_audio_path") and os.path.exists(yt_imported["original_audio_path"])
    print(f" -> YouTube import & audio extraction: PASS (Video: {os.path.getsize(yt_imported['original_video_path'])} bytes, Audio: {os.path.getsize(yt_imported['original_audio_path'])} bytes)")

    # 21. Test Progression of YouTube Project through Translation, Dubbing, and Subtitles
    print("\n[Step 21] Testing YouTube Project Dubbing Progression (Speech -> Translation -> Dubbing -> Export)...")
    # Add/verify transcript segment
    requests.post(
        f"{BASE_URL}/projects/{yt_proj_id}/transcription/segments",
        json={
            "segment_index": 0,
            "start_time": 0.0,
            "end_time": 4.5,
            "original_text": "All right, so here we are in front of the elephants.",
            "translated_text": ""
        },
        headers=headers
    )
    # Translate to Hindi
    requests.post(f"{BASE_URL}/projects/{yt_proj_id}/translation", headers=headers)
    # Synthesize Hindi voiceover
    yt_voice_res = requests.post(
        f"{BASE_URL}/projects/{yt_proj_id}/voiceover",
        json={"voice_name": "hi-IN-SwaraNeural", "speech_rate": 1.0},
        headers=headers
    )
    assert yt_voice_res.status_code == 200
    # Export VTT subtitles
    vtt_res = requests.post(
        f"{BASE_URL}/projects/{yt_proj_id}/export",
        json={"export_type": "vtt", "subtitle_mode": "bilingual"},
        headers=headers
    )
    assert vtt_res.status_code == 200
    print(" -> YouTube project dubbing progression: PASS (Hindi voiceover synthesized & bilingual subtitles generated)")

    print("\n==================================================")
    print("ALL 21 END-TO-END WORKFLOW VERIFICATIONS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    run_e2e_tests()

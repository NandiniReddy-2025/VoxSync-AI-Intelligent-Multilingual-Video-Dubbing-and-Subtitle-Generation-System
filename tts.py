import os
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth import get_optional_current_user
from config import AUDIO_DIR, TEMP_DIR
from languages import (
    get_available_voices,
    get_default_voice_for_language,
    validate_voice_for_language,
    get_translation_code,
    get_tts_locale,
    LANGUAGE_REGISTRY
)
from services.tts_service import generate_segment_audio
from services.audio_service import (
    build_timeline_dubbed_audio,
    run_ffmpeg,
    get_media_duration,
    check_audio_audibility,
    inspect_media_streams,
    get_audio_peak_volume
)

router = APIRouter(prefix="/api", tags=["tts"])

@router.get("/tts/voices")
def list_voices(language: Optional[str] = Query(None)):
    return get_available_voices(language)

@router.post("/projects/{project_id}/voiceover", response_model=schemas.ProjectDetailOut)
def generate_project_voiceover(
    project_id: str,
    request: schemas.GenerateVoiceoverRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    segments = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.project_id == project.id
    ).order_by(models.TranscriptSegment.segment_index).all()

    if not segments:
        raise HTTPException(status_code=400, detail="No segments found to generate speech.")

    # 1. Verify that all segments have valid translated text in the target language
    untranslated = [s for s in segments if not s.translated_text or not s.translated_text.strip()]
    if untranslated:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot generate dubbed voiceover: {len(untranslated)} of {len(segments)} segments "
                f"are missing translations in {project.target_language.upper()}. "
                "Please complete translation in Step 2 before generating voiceover."
            )
        )

    # Reject any placeholder strings
    placeholder_matches = [
        s for s in segments 
        if "demonstration of the imported" in (s.original_text or "").lower() 
        or "demonstration of the imported" in (s.translated_text or "").lower()
    ]
    if placeholder_matches:
        raise HTTPException(
            status_code=400,
            detail="Cannot dub video containing placeholder test transcripts. Please perform genuine speech recognition first."
        )

    # 2. Validate voice for the target language
    is_valid, resolved_voice, v_msg = validate_voice_for_language(
        project.target_language, 
        request.voice_name or project.voice_name
    )
    voice = resolved_voice

    project.voice_name = voice
    if request.speech_rate:
        project.speech_rate = request.speech_rate

    project.status = "generating_dubbed_voice"
    project.error_message = None
    db.commit()

    failed_segments = []

    # 3. Synthesize speech for every segment using ONLY the translated text
    for seg in segments:
        text = seg.translated_text.strip()
        slot_dur = seg.end_time - seg.start_time
        rate = seg.speech_rate or project.speech_rate or 1.0

        try:
            audio_path, duration, is_mismatch = generate_segment_audio(
                text=text,
                target_language=project.target_language,
                project_id=project.id,
                segment_id=seg.id,
                voice_name=voice,
                speech_rate=rate,
                slot_duration=slot_dur,
                original_text=seg.original_text,
                source_language=project.source_language
            )

            seg.audio_path = audio_path
            seg.audio_duration = duration
            seg.is_timing_mismatch = is_mismatch
            seg.status = "synthesized"
            seg.error_message = None

        except Exception as e:
            seg.audio_path = None
            seg.status = "failed"
            seg.error_message = str(e)
            failed_segments.append({
                "segment_index": seg.segment_index + 1,
                "id": seg.id,
                "error": str(e)
            })

    db.commit()

    # If ANY segment failed TTS, do not assemble a hollow/partial audio track
    if failed_segments:
        fail_summary = "; ".join([f"Segment #{f['segment_index']}: {f['error']}" for f in failed_segments[:5]])
        if len(failed_segments) > 5:
            fail_summary += f"... and {len(failed_segments) - 5} more"
        project.status = "failed"
        project.error_message = f"TTS synthesis failed for {len(failed_segments)} segment(s): {fail_summary}"
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=f"Speech synthesis failed for {len(failed_segments)} of {len(segments)} segments. {fail_summary}"
        )

    # 4. Assemble the full timeline dubbed audio track matching video duration
    try:
        target_dur = project.duration if project.duration > 0.1 else (segments[-1].end_time + 0.5)
        full_wav_path = str(AUDIO_DIR / f"full_dubbed_{project.id}.wav")
        full_mp3_path = str(AUDIO_DIR / f"full_dubbed_{project.id}.mp3")

        seg_dicts = [
            {
                "segment_index": s.segment_index,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "audio_path": s.audio_path
            }
            for s in segments
        ]
        build_timeline_dubbed_audio(seg_dicts, target_dur, full_wav_path)

        # Convert to high-quality MP3 for browser streaming & export
        run_ffmpeg(["-i", full_wav_path, "-b:a", "192k", "-y", full_mp3_path])

        if not os.path.exists(full_mp3_path) or os.path.getsize(full_mp3_path) < 1000:
            raise RuntimeError("Full dubbed audio MP3 conversion failed or produced empty file.")

        is_aud, aud_msg = check_audio_audibility(full_mp3_path)
        if not is_aud:
            raise RuntimeError(f"Assembled dubbed audio track failed audibility check: {aud_msg}")

        project.dubbed_audio_path = full_mp3_path
        project.status = "dubbed_audio_ready"
        project.error_message = None
        db.commit()
        db.refresh(project)
        return project

    except Exception as e:
        project.status = "failed"
        project.error_message = f"Timeline audio assembly failed: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=project.error_message)

@router.post("/projects/{project_id}/segments/{segment_id}/audio", response_model=schemas.SegmentOut)
def regenerate_segment_voice(
    project_id: str,
    segment_id: str,
    request: schemas.RegenerateSegmentAudioRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    seg = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.id == segment_id,
        models.TranscriptSegment.project_id == project_id
    ).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Strictly require valid translated text for synthesis
    if not seg.translated_text or not seg.translated_text.strip():
        raise HTTPException(
            status_code=400,
            detail=f"Segment translation is empty. Please translate this segment to {project.target_language.upper()} before synthesizing speech."
        )

    text = seg.translated_text.strip()
    is_valid, resolved_voice, v_msg = validate_voice_for_language(
        project.target_language,
        request.voice_name or project.voice_name
    )
    voice = resolved_voice

    rate = request.speech_rate or seg.speech_rate or project.speech_rate or 1.0
    slot_dur = seg.end_time - seg.start_time

    try:
        audio_path, duration, is_mismatch = generate_segment_audio(
            text=text,
            target_language=project.target_language,
            project_id=project.id,
            segment_id=seg.id,
            voice_name=voice,
            speech_rate=rate,
            slot_duration=slot_dur,
            original_text=seg.original_text,
            source_language=project.source_language
        )

        seg.audio_path = audio_path
        seg.audio_duration = duration
        seg.is_timing_mismatch = is_mismatch
        seg.speech_rate = rate
        seg.status = "synthesized"
        seg.error_message = None
        db.commit()

    except Exception as e:
        seg.status = "failed"
        seg.error_message = str(e)
        seg.audio_path = None
        db.commit()
        raise HTTPException(status_code=500, detail=f"Segment speech synthesis failed: {str(e)}")

    # Automatically re-assemble the full dubbed audio track ONLY IF all segments now have audio
    all_segs = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.project_id == project.id
    ).order_by(models.TranscriptSegment.segment_index).all()

    all_have_audio = all(s.audio_path and os.path.exists(s.audio_path) for s in all_segs)
    if all_have_audio:
        try:
            seg_dicts = [
                {
                    "segment_index": s.segment_index,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "audio_path": s.audio_path
                }
                for s in all_segs
            ]
            target_dur = project.duration if project.duration > 0.1 else (all_segs[-1].end_time + 0.5)
            full_wav_path = str(AUDIO_DIR / f"full_dubbed_{project.id}.wav")
            full_mp3_path = str(AUDIO_DIR / f"full_dubbed_{project.id}.mp3")
            build_timeline_dubbed_audio(seg_dicts, target_dur, full_wav_path)
            run_ffmpeg(["-i", full_wav_path, "-b:a", "192k", "-y", full_mp3_path])
            if os.path.exists(full_mp3_path) and os.path.getsize(full_mp3_path) > 500:
                project.dubbed_audio_path = full_mp3_path
            else:
                project.dubbed_audio_path = full_wav_path
            project.status = "dubbed_audio_ready"
            project.error_message = None
            db.commit()
        except Exception as e:
            print(f"Notice: full dubbed audio re-assembly notice: {e}")

    db.refresh(seg)
    return seg

@router.get("/projects/{project_id}/dubbing-diagnostics", response_model=schemas.DubbingDiagnosticsOut)
def get_dubbing_diagnostics(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    """
    Phase 7 Diagnostic Report: Comprehensive end-to-end tracing of all transcript segments,
    TTS statuses, assembled audio track, and FFmpeg master export stream properties.
    """
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    segments = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.project_id == project.id
    ).order_by(models.TranscriptSegment.segment_index).all()

    total_segments = len(segments)
    translated_count = 0
    synthesized_count = 0
    missing_count = 0
    failed_segment_ids = []
    seg_diagnostics = []

    for s in segments:
        has_trans = bool(s.translated_text and s.translated_text.strip() and s.translated_text != s.original_text)
        if has_trans:
            translated_count += 1
            trans_status = "translated"
        else:
            trans_status = "missing" if not s.translated_text else "untranslated"

        has_valid_audio = bool(s.audio_path and os.path.exists(s.audio_path) and os.path.getsize(s.audio_path) > 100)
        is_aud = False
        if has_valid_audio:
            synthesized_count += 1
            is_aud, _ = check_audio_audibility(s.audio_path)
            tts_status = "synthesized" if is_aud else "silent_audio"
        else:
            missing_count += 1
            tts_status = s.status if s.status in ["failed", "synthesizing"] else "missing_audio"
            failed_segment_ids.append(s.id)

        seg_diagnostics.append(
            schemas.SegmentDiagnostic(
                id=s.id,
                segment_index=s.segment_index,
                start_time=s.start_time,
                end_time=s.end_time,
                original_text=s.original_text,
                translated_text=s.translated_text or "",
                translation_status=trans_status,
                tts_status=tts_status,
                audio_path=s.audio_path,
                audio_duration=s.audio_duration,
                is_audible=is_aud,
                error_message=s.error_message
            )
        )

    # Assembled dubbed audio track inspection
    full_mp3_path = AUDIO_DIR / f"full_dubbed_{project.id}.mp3"
    full_wav_path = AUDIO_DIR / f"full_dubbed_{project.id}.wav"
    assembled_path = None
    if full_mp3_path.exists() and full_mp3_path.stat().st_size > 500:
        assembled_path = str(full_mp3_path)
    elif full_wav_path.exists() and full_wav_path.stat().st_size > 500:
        assembled_path = str(full_wav_path)
    elif project.dubbed_audio_path and os.path.exists(project.dubbed_audio_path):
        assembled_path = project.dubbed_audio_path

    assembled_ready = False
    assembled_dur = 0.0
    assembled_audible = False
    assembled_peak = None

    if assembled_path and os.path.exists(assembled_path):
        assembled_dur = get_media_duration(assembled_path)
        assembled_audible, _ = check_audio_audibility(assembled_path)
        assembled_peak = get_audio_peak_volume(assembled_path)
        assembled_ready = assembled_dur > 0.1 and assembled_audible

    # Export job & streams inspection
    last_video_export = db.query(models.ExportJob).filter(
        models.ExportJob.project_id == project.id,
        models.ExportJob.export_type == "video_dubbed"
    ).order_by(models.ExportJob.created_at.desc()).first()

    ffmpeg_export_status = last_video_export.status if last_video_export else None
    ffmpeg_errors = last_video_export.error_message if last_video_export else None
    video_stream_count = 0
    audio_stream_count = 0
    audio_codec = None
    final_playback_path = None
    final_playback_url = None

    if last_video_export and last_video_export.output_path and os.path.exists(last_video_export.output_path):
        final_playback_path = last_video_export.output_path
        filename = Path(final_playback_path).name
        final_playback_url = f"/api/media/stream/export/{filename}"
        streams = inspect_media_streams(final_playback_path)
        video_stream_count = len(streams.get("video_streams", []))
        audio_streams = streams.get("audio_streams", [])
        audio_stream_count = len(audio_streams)
        if audio_stream_count > 0:
            audio_codec = audio_streams[0].get("codec", "unknown")

    return schemas.DubbingDiagnosticsOut(
        project_id=project.id,
        project_title=project.title,
        source_language=project.source_language,
        target_language=project.target_language,
        translation_provider="Google Web Translate / MyMemory (with OpenAI/Gemini failover)",
        translation_source_code=get_translation_code(project.source_language, "google"),
        translation_target_code=get_translation_code(project.target_language, "google"),
        tts_provider="edge-tts (Neural)",
        selected_voice=project.voice_name or get_default_voice_for_language(project.target_language),
        tts_locale=get_tts_locale(project.target_language),
        verified_languages=list(LANGUAGE_REGISTRY.keys()),
        total_segments=total_segments,
        translated_segments=translated_count,
        synthesized_segments=synthesized_count,
        missing_segments=missing_count,
        failed_segment_ids=failed_segment_ids,
        segments_diagnostics=seg_diagnostics,
        assembled_audio_ready=assembled_ready,
        assembled_audio_path=assembled_path,
        assembled_audio_duration=round(assembled_dur, 2),
        assembled_audio_audible=assembled_audible,
        assembled_audio_peak_db=assembled_peak,
        export_status=project.status,
        ffmpeg_export_status=ffmpeg_export_status,
        ffmpeg_errors=ffmpeg_errors,
        video_stream_count=video_stream_count,
        audio_stream_count=audio_stream_count,
        audio_codec=audio_codec,
        final_playback_path=final_playback_path,
        final_playback_url=final_playback_url
    )

@router.get("/projects/{project_id}/dubbed-audio")
async def get_project_dubbed_audio(
    project_id: str,
    request: Request,
    v: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Stream full dubbed audio track for browser preview with HTTP Range support.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    full_mp3_path = AUDIO_DIR / f"full_dubbed_{project.id}.mp3"
    full_wav_path = AUDIO_DIR / f"full_dubbed_{project.id}.wav"

    audio_file = None
    if full_mp3_path.exists() and full_mp3_path.stat().st_size > 500:
        audio_file = full_mp3_path
    elif full_wav_path.exists() and full_wav_path.stat().st_size > 500:
        audio_file = full_wav_path
    elif project.dubbed_audio_path and os.path.exists(project.dubbed_audio_path):
        audio_file = Path(project.dubbed_audio_path)
    else:
        # Check if 100% of segments have valid audio
        segments = db.query(models.TranscriptSegment).filter(
            models.TranscriptSegment.project_id == project.id
        ).order_by(models.TranscriptSegment.segment_index).all()

        if segments and all(s.audio_path and os.path.exists(s.audio_path) for s in segments):
            seg_dicts = [
                {
                    "segment_index": s.segment_index,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "audio_path": s.audio_path
                }
                for s in segments
            ]
            target_dur = project.duration if project.duration > 0.1 else (segments[-1].end_time + 0.5)
            build_timeline_dubbed_audio(seg_dicts, target_dur, str(full_wav_path))
            run_ffmpeg(["-i", str(full_wav_path), "-b:a", "192k", "-y", str(full_mp3_path)])
            if full_mp3_path.exists() and full_mp3_path.stat().st_size > 500:
                audio_file = full_mp3_path
                project.dubbed_audio_path = str(full_mp3_path)
                db.commit()
            elif full_wav_path.exists() and full_wav_path.stat().st_size > 500:
                audio_file = full_wav_path
                project.dubbed_audio_path = str(full_wav_path)
                db.commit()

    if not audio_file or not audio_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Dubbed audio has not been fully generated yet. Please generate speech in Step 3."
        )

    file_size = audio_file.stat().st_size
    range_header = request.headers.get("range")
    content_type = "audio/mpeg" if audio_file.suffix.lower() == ".mp3" else "audio/wav"

    if range_header:
        range_str = range_header.replace("bytes=", "").strip()
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

        if start >= file_size or end >= file_size or start > end:
            return HTTPException(status_code=416, detail="Requested range not satisfiable")

        content_length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
            "Cache-Control": "no-cache",
        }

        def stream_file(p, s, l):
            with open(p, "rb") as f:
                f.seek(s)
                rem = l
                while rem > 0:
                    chunk = f.read(min(rem, 64 * 1024))
                    if not chunk:
                        break
                    rem -= len(chunk)
                    yield chunk

        return StreamingResponse(
            stream_file(audio_file, start, content_length),
            status_code=206,
            headers=headers
        )

    return FileResponse(
        path=str(audio_file),
        media_type=content_type,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
    )


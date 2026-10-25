from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth import get_optional_current_user
from services.transcription_service import transcribe_video_speech, retranscribe_segment_audio

router = APIRouter(prefix="/api/projects/{project_id}/transcription", tags=["transcription"])

@router.post("", response_model=schemas.ProjectDetailOut)
def transcribe_project(
    project_id: str,
    transcription_req: Optional[schemas.TranscriptionRequest] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.original_audio_path:
        raise HTTPException(status_code=400, detail="Please upload or import a video before transcribing.")

    # Concurrency guard: prevent duplicate jobs if already running
    if project.status == "transcribing":
        raise HTTPException(
            status_code=409, 
            detail="Transcription is already in progress for this video. Please wait for completion."
        )

    project.status = "transcribing"
    project.error_message = None
    db.commit()

    # Determine requested source language
    requested_lang = "auto"
    if transcription_req and transcription_req.source_language:
        requested_lang = transcription_req.source_language.strip()
    elif project.source_language and project.source_language.strip():
        requested_lang = project.source_language.strip()

    try:
        result = transcribe_video_speech(
            audio_path=project.original_audio_path,
            source_lang=requested_lang
        )

        raw_segments = result.get("segments", [])
        detected_lang = result.get("detected_language", "en")
        confidence = result.get("language_confidence", 1.0)

        # Clear existing segments for this project
        db.query(models.TranscriptSegment).filter(
            models.TranscriptSegment.project_id == project.id
        ).delete()

        # Add coherent sentence segments
        for seg in raw_segments:
            new_seg = models.TranscriptSegment(
                project_id=project.id,
                segment_index=seg["segment_index"],
                start_time=seg["start_time"],
                end_time=seg["end_time"],
                original_text=seg["original_text"],
                translated_text="",
                status="ready"
            )
            db.add(new_seg)

        # Update project language attributes
        project.detected_language = detected_lang
        project.language_confidence = confidence

        # If user selected auto or had no source language, set source_language to detected
        if requested_lang.lower() in ["auto", "detect", ""] or not project.source_language:
            project.source_language = detected_lang

        project.status = "transcribed"
        project.error_message = None
        db.commit()
        db.refresh(project)
        return project

    except Exception as e:
        project.status = "failed"
        project.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=f"Transcription failed: {str(e)}")

@router.post("/segments/{segment_id}/retry", response_model=schemas.SegmentOut)
def retry_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project or not project.original_audio_path:
        raise HTTPException(status_code=404, detail="Project or audio not found")

    seg = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.id == segment_id,
        models.TranscriptSegment.project_id == project_id
    ).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    try:
        new_text = retranscribe_segment_audio(
            audio_path=project.original_audio_path,
            start_time=seg.start_time,
            end_time=seg.end_time,
            source_lang=project.source_language
        )
        if new_text and new_text.strip():
            seg.original_text = new_text.strip()
            db.commit()
            db.refresh(seg)
        return seg
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to retry segment speech recognition: {str(e)}")

@router.patch("/segments/{segment_id}", response_model=schemas.SegmentOut)
def update_segment(
    project_id: str,
    segment_id: str,
    update_data: schemas.SegmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    seg = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.id == segment_id,
        models.TranscriptSegment.project_id == project_id
    ).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    if update_data.original_text is not None:
        seg.original_text = update_data.original_text
    if update_data.translated_text is not None:
        if update_data.translated_text.strip() != "" or not seg.translated_text:
            seg.translated_text = update_data.translated_text
    if update_data.start_time is not None:
        seg.start_time = update_data.start_time
    if update_data.end_time is not None:
        seg.end_time = update_data.end_time
    if update_data.speech_rate is not None:
        seg.speech_rate = update_data.speech_rate

    db.commit()
    db.refresh(seg)
    return seg

@router.post("/segments", response_model=schemas.SegmentOut)
def add_segment(
    project_id: str,
    segment_in: schemas.SegmentBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    new_seg = models.TranscriptSegment(
        project_id=project_id,
        segment_index=segment_in.segment_index,
        start_time=segment_in.start_time,
        end_time=segment_in.end_time,
        original_text=segment_in.original_text,
        translated_text=segment_in.translated_text or "",
        status="ready"
    )
    db.add(new_seg)
    db.commit()
    db.refresh(new_seg)
    return new_seg

@router.delete("/segments/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(
    project_id: str,
    segment_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    seg = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.id == segment_id,
        models.TranscriptSegment.project_id == project_id
    ).first()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    db.delete(seg)
    db.commit()
    return None

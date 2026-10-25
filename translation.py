from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth import get_optional_current_user
from services.translation_service import translate_single_text, translate_batch_texts

router = APIRouter(prefix="/api/projects/{project_id}/translation", tags=["translation"])

@router.post("", response_model=schemas.ProjectDetailOut)
def translate_project_segments(
    project_id: str,
    body: Optional[schemas.TranslateProjectRequest] = None,
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
        raise HTTPException(status_code=400, detail="No transcript segments found to translate.")

    if body and body.target_language:
        project.target_language = body.target_language

    target_lang = project.target_language or "te"
    source_lang = project.source_language or "en"

    project.status = "translating"
    project.error_message = None
    db.commit()

    try:
        # Process in chunks of 15 segments for fast batching and continuous DB saving
        chunk_size = 15
        for i in range(0, len(segments), chunk_size):
            chunk = segments[i:i + chunk_size]
            texts = [s.original_text or "" for s in chunk]
            translations = translate_batch_texts(
                texts=texts,
                source_lang=source_lang,
                target_lang=target_lang,
                chunk_size=chunk_size
            )
            for seg, trans in zip(chunk, translations):
                if trans and trans.strip():
                    seg.translated_text = trans.strip()
            # Commit after each batch to guarantee persistence
            db.commit()

        # Check total translated segments
        translated_count = sum(1 for s in segments if s.translated_text and s.translated_text.strip())
        if translated_count == 0 and len(segments) > 0:
            project.status = "failed"
            project.error_message = f"Failed to translate segments to {target_lang}. Translation providers unavailable."
            db.commit()
            raise HTTPException(
                status_code=502,
                detail=f"Translation failed. Could not translate segments to {target_lang}."
            )

        project.status = "translated"
        project.error_message = None
        db.commit()
        db.refresh(project)
        return project

    except HTTPException:
        raise
    except Exception as e:
        project.status = "failed"
        project.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Translation failed: {str(e)}")


@router.post("/segments/{segment_id}/retranslate", response_model=schemas.SegmentOut)
def retranslate_segment(
    project_id: str,
    segment_id: str,
    request_data: Optional[schemas.RetranslateSegmentRequest] = None,
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

    # If original_text is provided in the request payload, update it
    if request_data and request_data.original_text is not None and request_data.original_text.strip():
        seg.original_text = request_data.original_text.strip()

    target_lang = (
        request_data.target_language if request_data and request_data.target_language else None
    ) or project.target_language or "te"
    source_lang = project.source_language or "en"

    try:
        translated = translate_single_text(
            text=seg.original_text,
            source_lang=source_lang,
            target_lang=target_lang
        )
        if not translated or not translated.strip():
            raise ValueError(f"Translation provider returned empty translation for {target_lang}")

        seg.translated_text = translated.strip()
        db.commit()
        db.refresh(seg)
        return seg
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Retranslate failed: {str(e)}")


@router.patch("/segments/{segment_id}/translation", response_model=schemas.SegmentOut)
def update_segment_translation(
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

    if update_data.translated_text is not None:
        # Do not overwrite valid existing translation with an empty string
        if update_data.translated_text.strip() != "" or not seg.translated_text:
            seg.translated_text = update_data.translated_text
    db.commit()
    db.refresh(seg)
    return seg


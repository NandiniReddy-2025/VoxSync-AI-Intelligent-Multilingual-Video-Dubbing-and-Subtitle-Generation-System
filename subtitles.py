from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth import get_optional_current_user
from services.subtitle_service import generate_srt_content, generate_vtt_content

router = APIRouter(prefix="/api/projects/{project_id}/subtitles", tags=["subtitles"])

@router.get("/settings", response_model=schemas.SubtitleSettingOut)
def get_subtitle_settings(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    setting = db.query(models.SubtitleSetting).filter(
        models.SubtitleSetting.project_id == project_id
    ).first()
    if not setting:
        setting = models.SubtitleSetting(project_id=project_id)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting

@router.put("/settings", response_model=schemas.SubtitleSettingOut)
def update_subtitle_settings(
    project_id: str,
    update_data: schemas.SubtitleSettingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    setting = db.query(models.SubtitleSetting).filter(
        models.SubtitleSetting.project_id == project_id
    ).first()
    if not setting:
        setting = models.SubtitleSetting(project_id=project_id)
        db.add(setting)

    if update_data.font_family is not None:
        setting.font_family = update_data.font_family
    if update_data.font_size is not None:
        setting.font_size = update_data.font_size
    if update_data.primary_color is not None:
        setting.primary_color = update_data.primary_color
    if update_data.background_color is not None:
        setting.background_color = update_data.background_color
    if update_data.position is not None:
        setting.position = update_data.position
    if update_data.is_bilingual is not None:
        setting.is_bilingual = update_data.is_bilingual
    if update_data.embed_subtitles is not None:
        setting.embed_subtitles = update_data.embed_subtitles

    db.commit()
    db.refresh(setting)
    return setting

@router.get("/preview")
def preview_subtitles(
    project_id: str,
    format: str = Query("vtt", pattern="^(srt|vtt)$"),
    mode: str = Query("translated", pattern="^(original|translated|bilingual)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    segments = db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.project_id == project_id
    ).order_by(models.TranscriptSegment.segment_index).all()

    seg_dicts = [
        {
            "segment_index": s.segment_index,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "original_text": s.original_text,
            "translated_text": s.translated_text
        }
        for s in segments
    ]

    if format == "srt":
        content = generate_srt_content(seg_dicts, mode=mode)
    else:
        content = generate_vtt_content(seg_dicts, mode=mode)

    return {"format": format, "mode": mode, "content": content}

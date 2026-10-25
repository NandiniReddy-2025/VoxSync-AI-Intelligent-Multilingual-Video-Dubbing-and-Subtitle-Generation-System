import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth import get_optional_current_user
from config import SUPPORTED_LANGUAGES

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=List[schemas.ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    projects = db.query(models.Project).filter(
        models.Project.user_id == current_user.id
    ).order_by(models.Project.updated_at.desc()).all()
    return projects

@router.post("", response_model=schemas.ProjectDetailOut)
def create_project(
    project_in: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = models.Project(
        user_id=current_user.id,
        title=project_in.title,
        source_language=project_in.source_language or "en",
        target_language=project_in.target_language or "te",
        import_source=project_in.import_source or "upload",
        source_url=project_in.source_url,
        status="created"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Initialize default subtitle setting
    sub_setting = models.SubtitleSetting(
        project_id=project.id,
        font_family="Inter, sans-serif",
        font_size=24,
        primary_color="#FFFFFF",
        background_color="rgba(0,0,0,0.75)",
        position="bottom",
        is_bilingual=False,
        embed_subtitles=False
    )
    db.add(sub_setting)
    db.commit()
    db.refresh(project)

    return project

@router.get("/languages")
def get_languages():
    return SUPPORTED_LANGUAGES

@router.get("/{project_id}", response_model=schemas.ProjectDetailOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.patch("/{project_id}", response_model=schemas.ProjectDetailOut)
def update_project(
    project_id: str,
    project_update: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project_update.title is not None:
        project.title = project_update.title
    if project_update.source_language is not None:
        project.source_language = project_update.source_language
    if project_update.target_language is not None:
        project.target_language = project_update.target_language
    if project_update.voice_name is not None:
        project.voice_name = project_update.voice_name
    if project_update.speech_rate is not None:
        project.speech_rate = project_update.speech_rate

    db.commit()
    db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Clean up associated files if they exist
    for f in [project.original_video_path, project.original_audio_path]:
        if f and os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    db.delete(project)
    db.commit()
    return None

import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
import models, schemas
from auth import get_optional_current_user
from services.export_service import (
    export_srt_file,
    export_vtt_file,
    export_transcript_txt,
    export_full_dubbed_audio,
    export_combined_video
)

router = APIRouter(prefix="/api", tags=["export"])

class ProjectExportRequest(BaseModel):
    export_type: str  # "video_dubbed", "audio_dubbed", "srt", "vtt", "transcript_txt"
    embed_subtitles: Optional[bool] = False
    subtitle_mode: Optional[str] = "translated"  # "original", "translated", "bilingual"
    preserve_background_audio: Optional[bool] = False

@router.post("/projects/{project_id}/export", response_model=schemas.ExportJobOut)
def trigger_project_export(
    project_id: str,
    req: ProjectExportRequest,
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
        raise HTTPException(status_code=400, detail="Cannot export project without transcript segments.")

    seg_dicts = [
        {
            "segment_index": s.segment_index,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "original_text": s.original_text,
            "translated_text": s.translated_text,
            "audio_path": s.audio_path
        }
        for s in segments
    ]

    # Enforce zero-omission before video/audio dubbing export
    if req.export_type in ["video_dubbed", "audio_dubbed"]:
        missing_audio = [
            f"Segment #{s.segment_index + 1}"
            for s in segments
            if not s.audio_path or not os.path.exists(s.audio_path) or os.path.getsize(s.audio_path) < 100
        ]
        if missing_audio:
            summary = ", ".join(missing_audio[:6])
            if len(missing_audio) > 6:
                summary += f"... and {len(missing_audio) - 6} more"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot export dubbed media: {len(missing_audio)} of {len(segments)} segments "
                    f"are missing synthesized speech ({summary}). "
                    "Please synthesize all segments in Step 3 before exporting."
                )
            )

    subtitle_settings = None
    if project.subtitle_setting:
        subtitle_settings = {
            "font_family": project.subtitle_setting.font_family,
            "font_size": project.subtitle_setting.font_size,
            "primary_color": project.subtitle_setting.primary_color,
            "background_color": project.subtitle_setting.background_color,
            "position": project.subtitle_setting.position,
        }

    try:
        out_path = None
        file_name = None

        if req.export_type == "srt":
            out_path = export_srt_file(project.id, seg_dicts, mode=req.subtitle_mode or "translated")
            file_name = f"{Path(project.original_video_name or 'project').stem}_{req.subtitle_mode}.srt"

        elif req.export_type == "vtt":
            out_path = export_vtt_file(project.id, seg_dicts, mode=req.subtitle_mode or "translated")
            file_name = f"{Path(project.original_video_name or 'project').stem}_{req.subtitle_mode}.vtt"

        elif req.export_type == "transcript_txt":
            out_path = export_transcript_txt(project.id, seg_dicts)
            file_name = f"{Path(project.original_video_name or 'project').stem}_transcript.txt"

        elif req.export_type == "audio_dubbed":
            out_path = export_full_dubbed_audio(project.id, seg_dicts, project.duration)
            ext = Path(out_path).suffix
            file_name = f"{Path(project.original_video_name or 'project').stem}_dubbed{ext}"

        elif req.export_type == "video_dubbed":
            if not project.original_video_path or not os.path.exists(project.original_video_path):
                raise HTTPException(status_code=400, detail="Original video file is missing on server.")

            project.status = "exporting_video"
            db.commit()

            out_path = export_combined_video(
                project_id=project.id,
                original_video_path=project.original_video_path,
                segments=seg_dicts,
                total_duration=project.duration,
                embed_subtitles=bool(req.embed_subtitles),
                subtitle_mode=req.subtitle_mode or "translated",
                subtitle_settings=subtitle_settings,
                preserve_background_audio=bool(req.preserve_background_audio)
            )
            file_name = f"{Path(project.original_video_name or 'project').stem}_dubbed.mp4"
            project.status = "export_completed"
            project.error_message = None
            db.commit()

        else:
            raise HTTPException(status_code=400, detail=f"Unknown export type: {req.export_type}")

        file_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0

        # Save or update ExportJob
        job = models.ExportJob(
            project_id=project.id,
            export_type=req.export_type,
            output_path=out_path,
            file_name=file_name,
            file_size=file_size,
            status="completed"
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    except Exception as e:
        project.status = "failed"
        project.error_message = str(e)
        error_job = models.ExportJob(
            project_id=project.id,
            export_type=req.export_type,
            status="failed",
            error_message=str(e)
        )
        db.add(error_job)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/projects/{project_id}/exports", response_model=List[schemas.ExportJobOut])
def list_project_exports(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    exports = db.query(models.ExportJob).filter(
        models.ExportJob.project_id == project_id,
        models.ExportJob.status == "completed"
    ).order_by(models.ExportJob.created_at.desc()).all()
    # Filter to only jobs whose files actually exist on disk
    valid_exports = [e for e in exports if e.output_path and os.path.exists(e.output_path)]
    return valid_exports

@router.get("/exports/{export_id}/download")
def download_export_file(
    export_id: str,
    db: Session = Depends(get_db)
):
    job = db.query(models.ExportJob).filter(models.ExportJob.id == export_id).first()
    if not job or not job.output_path or not os.path.exists(job.output_path):
        raise HTTPException(status_code=404, detail="Export file not found or not yet generated.")

    return FileResponse(
        path=job.output_path,
        filename=job.file_name or os.path.basename(job.output_path),
        media_type="application/octet-stream"
    )

import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth import get_optional_current_user
from config import UPLOADS_DIR, AUDIO_DIR, EXPORTS_DIR, TEMP_DIR, STORAGE_DIR
from services.audio_service import extract_audio_from_video, get_media_duration

from services.youtube_service import fetch_youtube_metadata, download_youtube_media

router = APIRouter(prefix="/api/media", tags=["media"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE = 250 * 1024 * 1024  # 250 MB

@router.post("/youtube-info", response_model=schemas.YouTubeInfoOut)
def check_youtube_info(
    req: schemas.YouTubeImportRequest,
    current_user: models.User = Depends(get_optional_current_user)
):
    try:
        info = fetch_youtube_metadata(req.youtube_url)
        return info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube access error: {str(e)}")

@router.post("/projects/{project_id}/youtube-import", response_model=schemas.ProjectDetailOut)
async def import_youtube_video(
    project_id: str,
    req: schemas.YouTubeImportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        video_dest, audio_dest, duration, title = download_youtube_media(req.youtube_url, project.id)

        project.import_source = "youtube"
        project.source_url = req.youtube_url
        project.original_video_name = title
        project.original_video_path = video_dest
        project.original_audio_path = audio_dest
        project.duration = duration
        project.status = "uploaded"
        project.error_message = None
        project.dubbed_audio_path = None
        project.detected_language = None
        project.language_confidence = None

        # Cleanly purge any stale transcript segments from previous runs/experiments
        db.query(models.TranscriptSegment).filter(
            models.TranscriptSegment.project_id == project.id
        ).delete()

        db.commit()
        db.refresh(project)
        return project
    except ValueError as e:
        project.error_message = str(e)
        if not project.original_video_path:
            project.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        project.error_message = str(e)
        if not project.original_video_path:
            project.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"YouTube import failed: {str(e)}. If direct import is restricted, please upload an authorized local file."
        )

@router.post("/projects/{project_id}/upload", response_model=schemas.ProjectDetailOut)
async def upload_project_video(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_optional_current_user)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Save uploaded file
    safe_filename = f"{project.id}_{Path(file.filename).stem[:30]}{ext}"
    video_dest = UPLOADS_DIR / safe_filename

    total_bytes = 0
    with open(video_dest, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > MAX_FILE_SIZE:
                buffer.close()
                if video_dest.exists():
                    os.remove(video_dest)
                raise HTTPException(
                    status_code=400,
                    detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024*1024)} MB."
                )
            buffer.write(chunk)

    # Extract audio using FFmpeg
    try:
        audio_name = f"{project.id}_audio.wav"
        audio_dest = extract_audio_from_video(str(video_dest), output_name=audio_name)
        duration = get_media_duration(str(video_dest))
    except Exception as e:
        if video_dest.exists():
            os.remove(video_dest)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process video audio: {str(e)}"
        )

    # Update project record
    project.import_source = "upload"
    project.source_url = None
    project.original_video_name = file.filename
    project.original_video_path = str(video_dest)
    project.original_audio_path = audio_dest
    project.duration = round(duration, 2)
    project.status = "uploaded"
    project.error_message = None
    project.dubbed_audio_path = None
    project.detected_language = None
    project.language_confidence = None

    # Cleanly purge any stale transcript segments from previous runs/experiments
    db.query(models.TranscriptSegment).filter(
        models.TranscriptSegment.project_id == project.id
    ).delete()

    db.commit()
    db.refresh(project)
    return project

def range_stream(file_path: Path, start: int, end: int, chunk_size: int = 64 * 1024):
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data

@router.get("/stream/{media_type}/{filename}")
async def stream_media(media_type: str, filename: str, request: Request):
    """
    HTTP Range-capable streaming endpoint for video and audio playback.
    """
    # Prevent directory traversal
    clean_name = os.path.basename(filename)
    type_dirs = {
        "video": UPLOADS_DIR,
        "audio": AUDIO_DIR,
        "export": EXPORTS_DIR,
        "temp": TEMP_DIR,
    }
    target_dir = type_dirs.get(media_type)
    if not target_dir:
        raise HTTPException(status_code=400, detail="Invalid media type")

    file_path = target_dir / clean_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Requested media file not found")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    ext = file_path.suffix.lower()
    content_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".srt": "text/plain; charset=utf-8",
        ".vtt": "text/vtt; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    if range_header:
        # Parse range header e.g. "bytes=0-1048575"
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
        }
        return StreamingResponse(
            range_stream(file_path, start, end),
            status_code=206,
            headers=headers
        )

    # Regular full-file response
    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        headers={"Accept-Ranges": "bytes"}
    )

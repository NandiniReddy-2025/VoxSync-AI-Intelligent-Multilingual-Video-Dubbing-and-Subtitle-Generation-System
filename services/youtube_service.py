import os
import re
import gc
import time
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple
import yt_dlp

from config import UPLOADS_DIR, AUDIO_DIR, TEMP_DIR, FFMPEG_EXE
from services.audio_service import extract_audio_from_video, get_media_duration

YOUTUBE_REGEX = re.compile(
    r'^(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})(?:[?&].*)?$'
)

def extract_video_id(url: str) -> str:
    """Validate YouTube URL format and extract the 11-character video ID."""
    if not url or not isinstance(url, str):
        raise ValueError("Please provide a valid YouTube URL string.")
    
    url = url.strip()
    match = YOUTUBE_REGEX.match(url)
    if not match:
        raise ValueError(
            "Invalid YouTube URL format. Supported formats include: "
            "https://www.youtube.com/watch?v=VIDEO_ID, "
            "https://youtu.be/VIDEO_ID, or "
            "https://www.youtube.com/shorts/VIDEO_ID"
        )
    return match.group(1)

def get_ydl_base_opts() -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 3,
        'windowsfilenames': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb']
            }
        }
    }
    if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
        opts['ffmpeg_location'] = FFMPEG_EXE
    return opts

def fetch_youtube_metadata(url: str) -> Dict[str, Any]:
    """
    Fetch metadata for a YouTube URL and check access restrictions.
    Does not download the video media.
    """
    video_id = extract_video_id(url)
    clean_url = f"https://www.youtube.com/watch?v={video_id}"

    opts = get_ydl_base_opts()
    opts['extract_flat'] = False

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if not info:
                raise ValueError("Could not retrieve video information. The video may be unavailable or removed.")
            
            # Check availability / restrictions
            if info.get('is_live'):
                raise ValueError("Live streams are not supported for dubbing. Please import a finished on-demand video.")
            
            if info.get('availability') in ('private', 'needs_auth'):
                raise ValueError("This video is private or requires authentication to access.")
            
            duration = info.get('duration') or 0
            if duration > 900:  # 15 minutes max
                raise ValueError(
                    f"Video duration ({int(duration // 60)}m {int(duration % 60)}s) exceeds "
                    "the maximum allowed length of 15 minutes for automated dubbing."
                )

            return {
                "video_id": video_id,
                "title": info.get('title') or f"YouTube Video ({video_id})",
                "duration": round(float(duration), 2),
                "channel": info.get('uploader') or info.get('channel') or "Unknown Channel",
                "thumbnail": info.get('thumbnail'),
                "url": clean_url
            }

    except yt_dlp.utils.DownloadError as e:
        err_str = str(e).lower()
        if "private" in err_str:
            raise ValueError("This YouTube video is private and cannot be accessed.")
        elif "sign in" in err_str or "login" in err_str:
            raise ValueError("This YouTube video requires account authentication to access.")
        elif "age" in err_str or "restricted" in err_str:
            raise ValueError("This video has age/access restrictions and cannot be imported directly.")
        elif "drm" in err_str or "copyright" in err_str:
            raise ValueError("This video is DRM-protected and cannot be imported directly. Please upload an authorized local file.")
        elif "unavailable" in err_str:
            raise ValueError("This YouTube video is currently unavailable or has been removed.")
        else:
            raise ValueError(f"YouTube import failed: {str(e)}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Unable to access YouTube video: {str(e)}")

def safe_windows_move(src_path: Path, dst_path: Path, max_retries: int = 10, initial_delay: float = 0.25) -> str:
    """
    Safely moves a file from src_path to dst_path on Windows with exponential backoff
    and retry logic to overcome transient locks by antivirus, Windows Search Indexer,
    or OneDrive sync.
    """
    src = Path(src_path).resolve()
    dst = Path(dst_path).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Source file does not exist: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # If destination exists, attempt clean removal first
    if dst.exists():
        for _ in range(5):
            try:
                gc.collect()
                dst.unlink()
                break
            except (PermissionError, OSError):
                time.sleep(0.2)
        # If destination still cannot be removed, append unique token to prevent collision
        if dst.exists():
            dst = dst.parent / f"{dst.stem}_{uuid.uuid4().hex[:6]}{dst.suffix}"

    last_error = None
    for attempt in range(max_retries):
        try:
            gc.collect()
            shutil.move(str(src), str(dst))
            if dst.exists() and dst.stat().st_size > 0:
                return str(dst)
        except (PermissionError, OSError) as e:
            last_error = e
            # Exponential backoff sleep: 0.25s, 0.37s, 0.56s, 0.84s, 1.26s...
            time.sleep(initial_delay * (1.5 ** attempt))

    # Fallback: copy2 then unlink
    try:
        gc.collect()
        shutil.copy2(str(src), str(dst))
        if dst.exists() and dst.stat().st_size > 0:
            try:
                src.unlink()
            except Exception:
                pass
            return str(dst)
    except Exception as copy_err:
        last_error = copy_err

    raise OSError(
        f"Windows file lock prevented moving downloaded media: {last_error}. "
        "The file was temporarily locked by another system process (such as OneDrive or Antivirus)."
    )

def download_youtube_media(url: str, project_id: str) -> Tuple[str, str, float, str]:
    """
    Downloads YouTube video media into an isolated temporary directory outside OneDrive,
    verifies file completion and integrity, safely moves the finalized file to UPLOADS_DIR,
    and extracts the audio track for dubbing.
    Returns: (video_path, audio_path, duration, video_title)
    """
    meta = fetch_youtube_metadata(url)
    video_id = meta["video_id"]
    title = meta["title"]
    clean_url = meta["url"]

    # 1. Create a unique, isolated temporary directory for this specific import job outside OneDrive
    import_job_id = f"{project_id}_{uuid.uuid4().hex[:8]}"
    job_temp_dir = TEMP_DIR / "yt_downloads" / import_job_id
    job_temp_dir.mkdir(parents=True, exist_ok=True)

    # Final destination path in UPLOADS_DIR
    safe_title = "".join(c for c in title[:30] if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_filename = f"{project_id}_yt_{video_id}_{safe_title}.mp4"
    video_dest = UPLOADS_DIR / safe_filename

    # 2. Configure yt-dlp to download directly inside isolated job_temp_dir
    outtmpl = str(job_temp_dir / f"stream_{video_id}.%(ext)s")

    opts = get_ydl_base_opts()
    opts.update({
        'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'outtmpl': outtmpl,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'paths': {'home': str(job_temp_dir), 'temp': str(job_temp_dir)},
        'max_filesize': 250 * 1024 * 1024,
    })

    try:
        # 3. Wait for download library to report completion
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([clean_url])
    except Exception as e:
        shutil.rmtree(job_temp_dir, ignore_errors=True)
        raise ValueError(f"Failed to download YouTube video media: {str(e)}")

    try:
        # 4. Verify that the download succeeded and that completed media file exists with nonzero size
        candidate_files = [
            f for f in job_temp_dir.glob("*")
            if f.is_file() and not f.name.endswith(('.part', '.ytdl', '.temp'))
        ]
        if not candidate_files:
            raise ValueError("Download completed but no media file was produced in the temporary directory.")

        # Prefer .mp4 if merged, otherwise take the first valid media candidate
        mp4_candidates = [f for f in candidate_files if f.suffix.lower() == ".mp4"]
        actual_file = mp4_candidates[0] if mp4_candidates else candidate_files[0]

        file_size = actual_file.stat().st_size
        if file_size < 1024:
            raise ValueError(f"Downloaded media file is incomplete or corrupt ({file_size} bytes).")

        # 5 & 6. Verify file handle stability (no process writing)
        time.sleep(0.15)
        if actual_file.stat().st_size != file_size:
            time.sleep(0.5)

        # Ensure container is MP4
        final_temp_mp4 = actual_file
        if actual_file.suffix.lower() != ".mp4":
            remux_target = job_temp_dir / f"remuxed_{video_id}.mp4"
            cmd = [
                FFMPEG_EXE, "-y",
                "-i", str(actual_file),
                "-c:v", "copy",
                "-c:a", "aac",
                str(remux_target)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0 or not remux_target.exists():
                raise ValueError(f"Failed to convert downloaded media to MP4: {res.stderr.decode('utf-8', errors='ignore')}")
            final_temp_mp4 = remux_target

        # 7. Move completed file to its final destination using safe Windows-compatible operation
        final_video_path = safe_windows_move(final_temp_mp4, video_dest)

        # 8. Only then start FFmpeg probing, audio extraction, transcription, and remaining pipeline
        audio_name = f"{project_id}_audio.wav"
        audio_dest = extract_audio_from_video(final_video_path, output_name=audio_name)
        duration = get_media_duration(final_video_path)

        return final_video_path, audio_dest, round(duration, 2), title

    finally:
        # Clean up only current job's temporary directory
        shutil.rmtree(job_temp_dir, ignore_errors=True)

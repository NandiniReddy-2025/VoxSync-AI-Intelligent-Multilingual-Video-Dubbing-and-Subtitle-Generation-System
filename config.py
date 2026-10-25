import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# App Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "voxsync-super-secret-key-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'voxsync.db'}")

# Directories (Configurable via environment settings)
import tempfile

default_storage = BASE_DIR / "storage"
STORAGE_DIR = Path(os.getenv("VOXSYNC_STORAGE_DIR", str(default_storage))).resolve()
UPLOADS_DIR = STORAGE_DIR / "uploads"
AUDIO_DIR = STORAGE_DIR / "audio"
PROCESSED_DIR = STORAGE_DIR / "processed"
EXPORTS_DIR = STORAGE_DIR / "exports"

# Dedicated local application temporary directory outside OneDrive synchronization folders
def resolve_temp_dir() -> Path:
    env_temp = os.getenv("VOXSYNC_TEMP_DIR")
    if env_temp:
        return Path(env_temp).resolve()
    
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata and "onedrive" not in local_appdata.lower():
        return Path(local_appdata) / "VoxSyncAI" / "temp"
    
    return Path(tempfile.gettempdir()) / "VoxSyncAI" / "temp"

TEMP_DIR = resolve_temp_dir()

for d in [STORAGE_DIR, UPLOADS_DIR, AUDIO_DIR, PROCESSED_DIR, EXPORTS_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# FFmpeg resolution
def resolve_ffmpeg_path() -> str:
    # 1. Check system PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    
    # 2. Check imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass

    # 3. Common fallback locations
    candidates = [
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Users\hp\AppData\Local\Programs\Python\Python311\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    return "ffmpeg"

FFMPEG_EXE = resolve_ffmpeg_path()

# Optional AI API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Central Supported Languages configuration
from languages import get_supported_languages, LANGUAGE_REGISTRY
SUPPORTED_LANGUAGES = get_supported_languages()

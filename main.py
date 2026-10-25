import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import (
    FFMPEG_EXE,
    SUPPORTED_LANGUAGES,
    OPENAI_API_KEY,
    GEMINI_API_KEY
)
from database import engine, Base, SessionLocal
import models
from auth import get_password_hash

from routers import (
    auth,
    projects,
    media,
    transcription,
    translation,
    tts,
    subtitles,
    export
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Ensure columns exist in SQLite projects table
from sqlalchemy import text
with engine.connect() as conn:
    for col, col_type in [("import_source", "VARCHAR DEFAULT 'upload'"), ("source_url", "VARCHAR")]:
        try:
            conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {col_type}"))
            conn.commit()
        except Exception:
            pass

# Seed default demo account if no users
db = SessionLocal()
try:
    if db.query(models.User).count() == 0:
        demo_user = models.User(
            email="demo@voxsync.ai",
            hashed_password=get_password_hash("demo1234"),
            full_name="VoxSync Creator"
        )
        db.add(demo_user)
        db.commit()
finally:
    db.close()

app = FastAPI(
    title="VoxSync AI — Intelligent Multilingual Video Dubbing and Subtitle Generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS to allow frontend origins including port 5180
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5180",
    "http://localhost:5180",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(media.router)
app.include_router(transcription.router)
app.include_router(translation.router)
app.include_router(tts.router)
app.include_router(subtitles.router)
app.include_router(export.router)

@app.get("/api/health")
def health_check():
    ffmpeg_available = bool(FFMPEG_EXE and os.path.exists(FFMPEG_EXE))
    return {
        "status": "healthy",
        "service": "VoxSync AI Engine",
        "ffmpeg_status": "ready" if ffmpeg_available else "missing",
        "ffmpeg_path": FFMPEG_EXE if ffmpeg_available else None,
        "ai_providers": {
            "openai": bool(OPENAI_API_KEY),
            "gemini": bool(GEMINI_API_KEY),
            "edge_tts": True,
            "google_speech": True,
            "mymemory_translator": True
        },
        "supported_languages": list(SUPPORTED_LANGUAGES.keys())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)

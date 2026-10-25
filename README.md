# VoxSync AI — Intelligent Multilingual Video Dubbing and Subtitle Generation System

VoxSync AI is a full-stack, AI-powered web application that enables creators to import videos via local upload or YouTube, extract speech, generate timestamped transcripts, translate into multiple languages (Telugu, Hindi, Tamil, Kannada, Malayalam, Spanish, French, German, English), synthesize studio-grade neural voiceovers, synchronize subtitle files (SRT, WebVTT, embedded ASS), preview side-by-side comparisons, and export master dubbed media packages.

---

## ⚡ Simplified 4-Step Production Workflow

1. **Step 1: Import Video**
   - **Option 1: Upload from Device**: Drag-and-drop or file picker for local videos (MP4, MOV, MKV, WEBM, AVI up to 250MB) with upload progress and HTML5 playback preview.
   - **Option 2: Import from YouTube**: Pasted URL validation, access/DRM verification, public metadata inspection, automated stream retrieval, and 16kHz WAV audio extraction.
2. **Step 2: Transcribe, Translate & Edit**
   - Detect or select spoken source language and target dubbing language.
   - AI Speech-to-Text with timeline interval segmentation.
   - Side-by-side editing of original phrases and translated phrases with real-time segment re-translation.
3. **Step 3: Dub & Add Subtitles**
   - 300+ Microsoft Edge neural voices with customizable speech rates (0.8x - 1.3x).
   - Subtitle styling studio: font family, font size, primary color, background box, and on-screen position (bottom, middle, top).
   - Live synchronized video preview with real-time styled subtitle overlay (original, translated, or bilingual mode).
4. **Step 4: Preview & Export**
   - Synchronized side-by-side comparison player with audio toggle (original speech vs dubbed voiceover) and timeline scrubber.
   - One-click export for Master Dubbed Video (MP4) with optional burned-in embedded subtitles, Dubbed Audio (MP3), Subtitles (SRT & WebVTT), and Timestamped Plaintext Transcript (TXT).

---

## 🚀 Live Services & URLs

- **Frontend Application**: [http://127.0.0.1:5180/](http://127.0.0.1:5180/)
- **Backend API Docs (Swagger)**: [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs)
- **Backend Health Check**: [http://127.0.0.1:8010/api/health](http://127.0.0.1:8010/api/health)

---

## 🛠️ Tech Stack & Key Components

- **Frontend**: React 19, Vite, Vanilla CSS design system (curated indigo/slate light theme with glassmorphism), Lucide icons.
- **Backend**: Python 3.11, FastAPI, SQLAlchemy ORM, Uvicorn, Pydantic v2, yt-dlp.
- **Database**: SQLite (`voxsync.db`) with automatic table creation & migrations.
- **Audio/Video Processing**: FFmpeg 7.1 (bundled via `imageio-ffmpeg`), audio extraction (16kHz WAV), speed adjustment (`atempo`), timeline concatenation, video multiplexing.
- **Speech Recognition**: Silence-detection VAD + Google Speech Recognition + Whisper API compatibility.
- **Multilingual Translation**: Context-preserving translation engine supporting Telugu, Hindi, Tamil, Kannada, Malayalam, Spanish, French, German, and English.
- **Neural Text-to-Speech**: Microsoft Edge TTS (300+ studio-grade neural voices including Shruti & Mohan for Telugu, Swara & Madhur for Hindi, etc.).
- **Subtitles**: SRT, WebVTT, styled ASS subtitles (custom fonts, sizes, colors, positioning, bilingual support).

---

## 📋 Exact Setup & Launch Commands

### 1. Install Backend Dependencies
```powershell
cd backend
python -m pip install -r requirements.txt
```

### 2. Install Frontend Dependencies
```powershell
cd frontend
npm install
```

### 3. Start Backend Server
```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

### 4. Start Frontend Development Server
```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5180
```

---

## 🔑 Environment Variables (`backend/.env`)

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT token encryption key | `voxsync-ai-secret-key-development-2026` |
| `DATABASE_URL` | SQLAlchemy database connection string | `sqlite:///./voxsync.db` |
| `OPENAI_API_KEY` | *(Optional)* Enables Whisper API & GPT-4o translation | None (Free local models used) |
| `GEMINI_API_KEY` | *(Optional)* Enables Gemini 1.5 Flash translation | None (Free local models used) |

---

## 🧪 Automated End-to-End Verification

Run the automated test suite verifying all 21 core workflow capabilities:
```powershell
cd backend
python test_e2e.py
```

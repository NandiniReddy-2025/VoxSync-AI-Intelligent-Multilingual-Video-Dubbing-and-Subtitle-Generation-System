from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr

# Auth Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class TokenData(BaseModel):
    email: Optional[str] = None


# Segment Schemas
class SegmentBase(BaseModel):
    segment_index: int
    start_time: float
    end_time: float
    original_text: str
    translated_text: Optional[str] = ""

class SegmentUpdate(BaseModel):
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    speech_rate: Optional[float] = None

class SegmentOut(BaseModel):
    id: str
    project_id: str
    segment_index: int
    start_time: float
    end_time: float
    original_text: str
    translated_text: str
    audio_path: Optional[str] = None
    audio_duration: float
    is_timing_mismatch: bool
    speech_rate: float
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# Subtitle Settings Schemas
class SubtitleSettingUpdate(BaseModel):
    font_family: Optional[str] = "Inter, sans-serif"
    font_size: Optional[int] = 24
    primary_color: Optional[str] = "#FFFFFF"
    background_color: Optional[str] = "rgba(0,0,0,0.75)"
    position: Optional[str] = "bottom"
    is_bilingual: Optional[bool] = False
    embed_subtitles: Optional[bool] = False

class SubtitleSettingOut(BaseModel):
    id: str
    project_id: str
    font_family: str
    font_size: int
    primary_color: str
    background_color: str
    position: str
    is_bilingual: bool
    embed_subtitles: bool

    class Config:
        from_attributes = True


# Export Schemas
class ExportJobOut(BaseModel):
    id: str
    project_id: str
    export_type: str
    output_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ExportRequest(BaseModel):
    embed_subtitles: bool = False
    subtitle_type: str = "translated"  # "original", "translated", "bilingual"


# Project Schemas
class ProjectCreate(BaseModel):
    title: str
    source_language: Optional[str] = "en"
    target_language: Optional[str] = "te"
    import_source: Optional[str] = "upload"
    source_url: Optional[str] = None

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    voice_name: Optional[str] = None
    speech_rate: Optional[float] = None

class YouTubeImportRequest(BaseModel):
    youtube_url: str

class YouTubeInfoOut(BaseModel):
    video_id: str
    title: str
    duration: float
    channel: str
    thumbnail: Optional[str] = None
    url: str

class ProjectOut(BaseModel):
    id: str
    user_id: str
    title: str
    original_video_name: Optional[str] = None
    duration: float
    source_language: str
    target_language: str
    detected_language: Optional[str] = None
    language_confidence: Optional[float] = None
    voice_name: Optional[str] = None
    speech_rate: float
    import_source: Optional[str] = "upload"
    source_url: Optional[str] = None
    dubbed_audio_path: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ProjectDetailOut(ProjectOut):
    original_video_path: Optional[str] = None
    original_audio_path: Optional[str] = None
    dubbed_audio_path: Optional[str] = None
    segments: List[SegmentOut] = []
    subtitle_setting: Optional[SubtitleSettingOut] = None
    exports: List[ExportJobOut] = []

    class Config:
        from_attributes = True


# Operations
class TranscriptionRequest(BaseModel):
    source_language: Optional[str] = "auto"
    model_size: Optional[str] = "base"

class RetranslateSegmentRequest(BaseModel):
    segment_id: Optional[str] = None
    original_text: Optional[str] = None
    target_language: Optional[str] = None

class TranslateProjectRequest(BaseModel):
    target_language: Optional[str] = None

class GenerateVoiceoverRequest(BaseModel):
    voice_name: Optional[str] = None
    speech_rate: Optional[float] = 1.0

class RegenerateSegmentAudioRequest(BaseModel):
    voice_name: Optional[str] = None
    speech_rate: Optional[float] = 1.0


class SegmentDiagnostic(BaseModel):
    id: str
    segment_index: int
    start_time: float
    end_time: float
    original_text: str
    translated_text: str
    translation_status: str
    tts_status: str
    audio_path: Optional[str] = None
    audio_duration: float
    is_audible: bool
    error_message: Optional[str] = None


class DubbingDiagnosticsOut(BaseModel):
    project_id: str
    project_title: str
    source_language: str
    target_language: str
    translation_provider: Optional[str] = "Google Web Translate / MyMemory (with OpenAI/Gemini failover)"
    translation_source_code: Optional[str] = "en"
    translation_target_code: Optional[str] = "te"
    tts_provider: Optional[str] = "edge-tts (Neural)"
    selected_voice: Optional[str] = None
    tts_locale: Optional[str] = None
    verified_languages: Optional[List[str]] = None
    total_segments: int
    translated_segments: int
    synthesized_segments: int
    missing_segments: int
    failed_segment_ids: List[str]
    segments_diagnostics: List[SegmentDiagnostic]
    assembled_audio_ready: bool
    assembled_audio_path: Optional[str] = None
    assembled_audio_duration: float
    assembled_audio_audible: bool
    assembled_audio_peak_db: Optional[float] = None
    export_status: str
    ffmpeg_export_status: Optional[str] = None
    ffmpeg_errors: Optional[str] = None
    video_stream_count: int
    audio_stream_count: int
    audio_codec: Optional[str] = None
    final_playback_path: Optional[str] = None
    final_playback_url: Optional[str] = None


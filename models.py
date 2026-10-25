import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    original_video_name = Column(String, nullable=True)
    original_video_path = Column(String, nullable=True)
    original_audio_path = Column(String, nullable=True)
    dubbed_audio_path = Column(String, nullable=True)
    duration = Column(Float, default=0.0)
    source_language = Column(String, default="en")
    target_language = Column(String, default="te")
    detected_language = Column(String, nullable=True)
    language_confidence = Column(Float, nullable=True)
    voice_name = Column(String, nullable=True)
    speech_rate = Column(Float, default=1.0)
    import_source = Column(String, default="upload")  # "upload" | "youtube"
    source_url = Column(String, nullable=True)
    status = Column(String, default="uploaded")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="projects")
    segments = relationship("TranscriptSegment", back_populates="project", cascade="all, delete-orphan", order_by="TranscriptSegment.segment_index")
    subtitle_setting = relationship("SubtitleSetting", back_populates="project", uselist=False, cascade="all, delete-orphan")
    exports = relationship("ExportJob", back_populates="project", cascade="all, delete-orphan")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    segment_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)  # in seconds
    end_time = Column(Float, nullable=False)    # in seconds
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, default="")
    audio_path = Column(String, nullable=True)
    audio_duration = Column(Float, default=0.0)
    is_timing_mismatch = Column(Boolean, default=False)
    speech_rate = Column(Float, default=1.0)
    status = Column(String, default="ready")
    error_message = Column(Text, nullable=True)

    project = relationship("Project", back_populates="segments")


class SubtitleSetting(Base):
    __tablename__ = "subtitle_settings"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, unique=True)
    font_family = Column(String, default="Inter, sans-serif")
    font_size = Column(Integer, default=24)
    primary_color = Column(String, default="#FFFFFF")
    background_color = Column(String, default="rgba(0,0,0,0.75)")
    position = Column(String, default="bottom")  # "bottom", "top", "middle"
    is_bilingual = Column(Boolean, default=False)
    embed_subtitles = Column(Boolean, default=False)

    project = relationship("Project", back_populates="subtitle_setting")


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    export_type = Column(String, nullable=False)  # "video_dubbed", "audio_dubbed", "srt", "vtt", "transcript_txt"
    output_path = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, default=0)
    status = Column(String, default="pending")  # "pending", "completed", "failed"
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="exports")

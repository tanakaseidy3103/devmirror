"""
DevMirror - SQLAlchemy データベースモデル
"""
import json
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.domain.models import IncidentStatus, TestResult


class ProjectModel(Base):
    """プロジェクトテーブル"""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    language = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    git_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    fingerprints = relationship("FingerprintModel", back_populates="project")
    incidents = relationship("IncidentModel", back_populates="project")


class FingerprintModel(Base):
    """Environment Fingerprintテーブル"""
    __tablename__ = "fingerprints"

    id = Column(Integer, primary_key=True, index=True)
    fingerprint_id = Column(String(36), unique=True, nullable=False, index=True)
    environment_name = Column(String(255), nullable=False)
    schema_version = Column(String(16), default="1.0")
    collected_at = Column(DateTime, default=datetime.utcnow)

    # JSONとして保存
    os_info = Column(JSON, nullable=True)
    architecture_info = Column(JSON, nullable=True)
    runtime_info = Column(JSON, nullable=True)
    compiler_info = Column(JSON, nullable=True)
    dependencies = Column(JSON, default=list)
    project_info = Column(JSON, nullable=True)
    path_entries = Column(JSON, default=list)
    raw_metadata = Column(JSON, default=dict)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    project = relationship("ProjectModel", back_populates="fingerprints")


class DiffModel(Base):
    """Environment Diffテーブル"""
    __tablename__ = "diffs"

    id = Column(Integer, primary_key=True, index=True)
    diff_id = Column(String(36), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    fingerprint_a_id = Column(String(36), nullable=False)
    fingerprint_b_id = Column(String(36), nullable=False)
    environment_a_name = Column(String(255), nullable=False)
    environment_b_name = Column(String(255), nullable=False)

    entries = Column(JSON, default=list)
    high_severity_count = Column(Integer, default=0)
    medium_severity_count = Column(Integer, default=0)
    low_severity_count = Column(Integer, default=0)


class IncidentModel(Base):
    """Incident Capsuleテーブル"""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(16), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project_name = Column(String(255), nullable=False)
    project_language = Column(String(64), nullable=True)
    git_commit = Column(String(64), nullable=True)
    git_branch = Column(String(128), nullable=True)

    environment_name = Column(String(255), nullable=False)
    fingerprint_id = Column(String(36), nullable=True)
    diff_id = Column(String(36), nullable=True)

    test_result = Column(Enum(TestResult), default=TestResult.UNKNOWN)
    command_executed = Column(Text, nullable=True)
    build_result = Column(Text, nullable=True)

    logs = Column(Text, default="")
    error_messages = Column(JSON, default=list)
    stack_traces = Column(JSON, default=list)
    screenshots = Column(JSON, default=list)

    ai_diagnosis = Column(JSON, nullable=True)
    status = Column(Enum(IncidentStatus), default=IncidentStatus.OPEN)
    timeline = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    notes = Column(Text, default="")

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    project = relationship("ProjectModel", back_populates="incidents")

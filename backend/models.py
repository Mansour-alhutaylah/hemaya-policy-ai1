from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    phone = Column(String, nullable=True)
    role = Column(String, default="user")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    settings = Column(JSONB, nullable=True)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    file_name = Column(String)
    description = Column(Text, nullable=True)
    department = Column(String, nullable=True)
    version = Column(String, default="1.0")
    status = Column(String, default="uploaded")
    file_url = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    content_preview = Column(Text, nullable=True)
    framework_code = Column(String, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    results = relationship("ComplianceResult", back_populates="policy", cascade="all, delete-orphan")
    gaps = relationship("Gap", back_populates="policy", cascade="all, delete-orphan")
    mappings = relationship("MappingReview", back_populates="policy", cascade="all, delete-orphan")


class ControlLibrary(Base):
    __tablename__ = "control_library"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    framework = Column(String, index=True)
    control_code = Column(String)
    title = Column(String)
    keywords = Column(JSONB)
    severity_if_missing = Column(String, default="Medium")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    policy_id = Column(UUID(as_uuid=False), ForeignKey("policies.id"))
    framework = Column(String)
    compliance_score = Column(Float)
    controls_covered = Column(Integer, default=0)
    controls_partial = Column(Integer, default=0)
    controls_missing = Column(Integer, default=0)
    status = Column(String)
    analyzed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    analysis_duration = Column(Float, default=0)
    details = Column(JSONB)

    policy = relationship("Policy", back_populates="results")


class Gap(Base):
    __tablename__ = "gaps"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    policy_id = Column(UUID(as_uuid=False), ForeignKey("policies.id"))
    framework = Column(String)
    control_id = Column(String)
    control_name = Column(String)
    severity = Column(String, default="Medium")
    status = Column(String, default="Open")
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    owner = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    policy = relationship("Policy", back_populates="gaps")


class MappingReview(Base):
    __tablename__ = "mapping_reviews"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    policy_id = Column(UUID(as_uuid=False), ForeignKey("policies.id"))
    control_id = Column(String)
    framework = Column(String)
    evidence_snippet = Column(Text, nullable=True)
    confidence_score = Column(Float, default=0)
    ai_rationale = Column(Text, nullable=True)
    decision = Column(String, default="Pending")
    review_notes = Column(Text, nullable=True)
    reviewer = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    policy = relationship("Policy", back_populates="mappings")


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    policy_id = Column(UUID(as_uuid=False), ForeignKey("policies.id"), nullable=True)
    report_type = Column(String)
    format = Column(String)
    status = Column(String, default="Completed")
    download_url = Column(String, nullable=True)
    frameworks_included = Column(JSONB, nullable=True)
    generated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    actor = Column(String)
    action = Column(String)
    target_type = Column(String)
    target_id = Column(String)
    details = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    policy_id = Column(UUID(as_uuid=False), ForeignKey("policies.id"))
    insight_type = Column(String)
    title = Column(String)
    description = Column(Text, nullable=True)
    priority = Column(String)
    confidence = Column(Float, default=0)
    status = Column(String, default="New")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Framework(Base):
    __tablename__ = "frameworks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    name = Column(String, unique=True)
    description = Column(Text, nullable=True)

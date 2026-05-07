from datetime import datetime, timezone
import uuid


def _now():
    return datetime.now(timezone.utc)

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from .database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    phone = Column(String, nullable=True)
    role = Column(String, default="user")
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    settings = Column(JSON, nullable=True)


class OTPToken(Base):
    __tablename__ = "otp_tokens"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    otp_hash = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    otp_hash = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(String, primary_key=True, default=generate_uuid)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    file_name = Column(String)
    description = Column(Text, nullable=True)
    department = Column(String, nullable=True)
    version = Column(String, default="1.0")
    status = Column(String, default="uploaded")
    file_url = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    content_preview = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=_now)
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    # Real-time processing progress (0..100). Updated at each pipeline stage
    # (text extraction, chunking, embedding, control analysis, etc.) so the
    # frontend can show an accurate "Processing • 45%" indicator. Persisted
    # to the DB so refresh shows the latest value.
    progress = Column(Integer, default=0, nullable=True)
    progress_stage = Column(String, nullable=True)

    # Cooperative pause: the analyzer polls pause_requested at safe checkpoints
    # (after each framework finishes). When true, it commits, sets status to
    # 'paused', records paused_at, clears the flag, and exits gracefully.
    # Resume re-runs the analyzer with resume=True; frameworks that already
    # have a compliance_results row are skipped, and the verification_cache
    # makes any re-run framework cheap.
    pause_requested = Column(Boolean, default=False, nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)

    results = relationship("ComplianceResult", back_populates="policy", cascade="all, delete-orphan")
    gaps = relationship("Gap", back_populates="policy", cascade="all, delete-orphan")
    mappings = relationship("MappingReview", back_populates="policy", cascade="all, delete-orphan")


class ControlLibrary(Base):
    __tablename__ = "control_library"

    id = Column(String, primary_key=True, default=generate_uuid)
    framework_id = Column(String, ForeignKey("frameworks.id"), index=True)
    control_code = Column(String)
    title = Column(String)
    keywords = Column(JSON)
    severity_if_missing = Column(String, default="Medium")
    created_at = Column(DateTime(timezone=True), default=_now)


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(String, ForeignKey("policies.id"))
    framework_id = Column(String, ForeignKey("frameworks.id"))
    compliance_score = Column(Float)
    controls_covered = Column(Integer, default=0)
    controls_partial = Column(Integer, default=0)
    controls_missing = Column(Integer, default=0)
    status = Column(String)
    analyzed_at = Column(DateTime(timezone=True), default=_now)
    analysis_duration = Column(Float, default=0)
    details = Column(JSON)

    policy = relationship("Policy", back_populates="results")


class Gap(Base):
    __tablename__ = "gaps"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(String, ForeignKey("policies.id"))
    framework_id = Column(String, ForeignKey("frameworks.id"))
    control_id = Column(String, ForeignKey("control_library.id"))
    control_name = Column(String)
    severity = Column(String, default="Medium")
    status = Column(String, default="Open")
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    remediation_notes = Column(Text, nullable=True)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    # Soft reference to the mapping_review that produced this gap (no FK
    # constraint so gap rows survive when mapping_reviews are replaced on re-analysis).
    mapping_id = Column(String, nullable=True)
    # Human-readable owner assigned during gap triage (not a user FK, so the
    # reviewer can type any name / email without needing a user account).
    owner_name = Column(String, nullable=True)

    policy = relationship("Policy", back_populates="gaps")


class MappingReview(Base):
    __tablename__ = "mapping_reviews"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(String, ForeignKey("policies.id"))
    control_id = Column(String, ForeignKey("control_library.id"))
    framework_id = Column(String, ForeignKey("frameworks.id"))
    evidence_snippet = Column(Text, nullable=True)
    confidence_score = Column(Float, default=0)
    ai_rationale = Column(Text, nullable=True)
    decision = Column(String, default="Pending")
    review_notes = Column(Text, nullable=True)
    reviewer_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    policy = relationship("Policy", back_populates="mappings")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(String, ForeignKey("policies.id"), nullable=True)
    report_type = Column(String)
    format = Column(String)
    status = Column(String, default="Completed")
    download_url = Column(String, nullable=True)
    frameworks_included = Column(JSON, nullable=True)
    generated_at = Column(DateTime(timezone=True), default=_now)
    created_at = Column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    actor_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String)
    target_type = Column(String)
    target_id = Column(String)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_now)


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(String, ForeignKey("policies.id"))
    insight_type = Column(String)
    title = Column(String)
    description = Column(Text, nullable=True)
    priority = Column(String)
    confidence = Column(Float, default=0)
    status = Column(String, default="New")
    created_at = Column(DateTime(timezone=True), default=_now)


class Framework(Base):
    __tablename__ = "frameworks"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True)
    description = Column(Text, nullable=True)

    # File-document fields. Frameworks are uploaded reference documents,
    # so each row points at the actual stored PDF/DOCX/TXT.
    version = Column(String, nullable=True)
    original_file_name = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

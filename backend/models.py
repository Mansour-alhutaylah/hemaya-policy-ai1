from datetime import datetime, timezone
import uuid


def _now():
    return datetime.now(timezone.utc)

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
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

    # Remediation relationships (lazy-evaluated string refs avoid forward-ref issues)
    created_drafts  = relationship(
        "RemediationDraft",
        foreign_keys="[RemediationDraft.created_by]",
        back_populates="creator",
        lazy="dynamic",
    )
    reviewed_drafts = relationship(
        "RemediationDraft",
        foreign_keys="[RemediationDraft.reviewed_by]",
        back_populates="reviewer_user",
        lazy="dynamic",
    )
    created_versions = relationship(
        "PolicyVersion",
        foreign_keys="[PolicyVersion.created_by]",
        back_populates="creator",
        lazy="dynamic",
    )


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
    remediation_drafts = relationship("RemediationDraft", back_populates="policy", cascade="all, delete-orphan")
    policy_versions = relationship("PolicyVersion", back_populates="policy", cascade="all, delete-orphan")


class ControlLibrary(Base):
    __tablename__ = "control_library"

    id = Column(String, primary_key=True, default=generate_uuid)
    framework_id = Column(String, ForeignKey("frameworks.id"), index=True)
    control_code = Column(String)
    title = Column(String)
    keywords = Column(JSON)
    severity_if_missing = Column(String, default="Medium")
    created_at = Column(DateTime(timezone=True), default=_now)

    remediation_drafts = relationship(
        "RemediationDraft",
        back_populates="control",
        lazy="dynamic",
    )


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
    remediation_drafts = relationship(
        "RemediationDraft",
        back_populates="mapping_review",
        lazy="dynamic",
    )


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

    remediation_drafts = relationship(
        "RemediationDraft",
        back_populates="framework",
        lazy="dynamic",
    )


# Valid values: "draft" | "under_review" | "approved" | "rejected" | "superseded"
REMEDIATION_STATUSES = {"draft", "under_review", "approved", "rejected", "superseded"}

# Valid values: "original" | "ai_draft" | "ai_remediated" | "final"
#   ai_draft       — per-control additive draft (one missing checkpoint at a time)
#   ai_remediated  — full-policy improved version (consolidated, addresses all
#                    partial / non-compliant controls in the latest analysis)
VERSION_TYPES = {"original", "ai_draft", "ai_remediated", "final"}


class RemediationDraft(Base):
    """
    AI-generated policy ADDITIONS that address a specific compliance gap.

    ARCHITECTURAL CONSTRAINT: suggested_policy_text contains ONLY the new
    sections to append — never a full policy rewrite. The original policy
    is never modified; this row is always a separate additive draft.
    """
    __tablename__ = "remediation_drafts"

    # Compound indexes support the three most common query patterns:
    #   1. All drafts for a policy              → (policy_id)
    #   2. Drafts by lifecycle status           → (remediation_status)
    #   3. Active drafts for a policy           → (policy_id, remediation_status)
    #   4. Which control triggered this draft   → (control_id)
    #   5. Which framework this draft targets   → (framework_id)
    __table_args__ = (
        Index("ix_rd_policy_status",  "policy_id", "remediation_status"),
        Index("ix_rd_control_id",     "control_id"),
        Index("ix_rd_framework_id",   "framework_id"),
        Index("ix_rd_created_at",     "created_at"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(
        String, ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Nullable: drafts can be requested ad-hoc without a prior mapping review.
    mapping_review_id = Column(
        String, ForeignKey("mapping_reviews.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    control_id = Column(
        String, ForeignKey("control_library.id", ondelete="SET NULL"),
        nullable=True,
    )
    framework_id = Column(
        String, ForeignKey("frameworks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Immutable snapshot of what was missing at time of generation.
    missing_requirements = Column(JSON, nullable=False)       # list[str]
    ai_rationale         = Column(Text, nullable=True)
    # The additive-only text generated by the AI.
    suggested_policy_text = Column(Text, nullable=False)
    # Top-level section titles extracted from suggested_policy_text.
    section_headers = Column(JSON, nullable=True)             # list[str]
    # Lifecycle: draft → under_review → approved | rejected | superseded
    remediation_status = Column(String, default="draft", nullable=False, index=True)
    review_notes       = Column(Text, nullable=True)
    # Two separate FKs to users: who created vs who reviewed.
    created_by  = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), default=_now)
    updated_at  = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    # ── ORM relationships ─────────────────────────────────────────────────────
    policy         = relationship("Policy",         back_populates="remediation_drafts")
    mapping_review = relationship("MappingReview",  back_populates="remediation_drafts")
    control        = relationship("ControlLibrary", back_populates="remediation_drafts")
    framework      = relationship("Framework",      back_populates="remediation_drafts")
    policy_versions = relationship("PolicyVersion", back_populates="remediation_draft")

    # Disambiguate the two FK paths to the users table.
    creator      = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_drafts",
    )
    reviewer_user = relationship(
        "User",
        foreign_keys=[reviewed_by],
        back_populates="reviewed_drafts",
    )


class PolicyVersion(Base):
    """
    Immutable append-only audit record of a policy's content at a point in time.

    Lifecycle:
      version_type = "original"  — written once at upload; NEVER modified.
      version_type = "ai_draft"  — auto-created by the remediation engine;
                                    contains ONLY the additive sections.
      version_type = "final"     — created by a human approving a draft;
                                    represents the merged, publishable document.

    The UNIQUE constraint on (policy_id, version_number) at the DB level
    guarantees monotonic versioning even under concurrent requests.
    """
    __tablename__ = "policy_versions"

    # Query patterns supported:
    #   1. All versions for a policy          → (policy_id)
    #   2. Latest version of a given type     → (policy_id, version_type)
    #   3. Audit timeline                     → (policy_id, version_number)
    __table_args__ = (
        Index("ix_pv_policy_type",    "policy_id", "version_type"),
        Index("ix_pv_policy_version", "policy_id", "version_number"),
        Index("ix_pv_version_type",   "version_type"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(
        String, ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Monotonically increasing within a policy; version 1 = original upload.
    version_number       = Column(Integer, nullable=False)
    version_type         = Column(String, nullable=False)   # original | ai_draft | final
    content              = Column(Text, nullable=False)
    compliance_score     = Column(Float, nullable=True)
    # Traceable link back to the draft that produced this version (null for originals).
    remediation_draft_id = Column(
        String, ForeignKey("remediation_drafts.id", ondelete="SET NULL"),
        nullable=True,
    )
    change_summary = Column(Text, nullable=True)
    created_by     = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=_now)

    # ── ORM relationships ─────────────────────────────────────────────────────
    policy            = relationship("Policy",           back_populates="policy_versions")
    remediation_draft = relationship("RemediationDraft", back_populates="policy_versions")
    creator           = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_versions",
    )

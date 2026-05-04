import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# Enforces: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special character.
_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@#$%^&*!?_\-+=<>]).{8,64}$'
)


def _check_password_strength(v: str) -> str:
    if not _PASSWORD_RE.match(v):
        raise ValueError(
            "Password must be 8–64 characters and include at least one uppercase letter, "
            "one lowercase letter, one number, and one special character (@#$%^&*!?_-+=<>)."
        )
    return v


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: str
    password: str = Field(min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _check_password_strength(v)


class UserBase(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class User(UserBase):
    id: Any
    role: str
    settings: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PolicyBase(BaseModel):
    file_name: Optional[str] = None
    description: Optional[str] = None
    department: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    file_url: Optional[str] = None
    file_type: Optional[str] = None
    content_preview: Optional[str] = None


class PolicyCreate(PolicyBase):
    pass


class Policy(PolicyBase):
    id: str
    uploaded_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ComplianceResult(BaseModel):
    id: str
    policy_id: str
    framework_id: Optional[str] = None
    compliance_score: float
    controls_covered: int
    controls_partial: int
    controls_missing: int
    status: str
    analyzed_at: datetime
    analysis_duration: Optional[float] = 0
    details: Optional[Any] = None

    class Config:
        from_attributes = True


class Gap(BaseModel):
    id: str
    policy_id: str
    framework_id: Optional[str] = None
    control_id: Optional[str] = None
    control_name: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    remediation: Optional[str] = None
    remediation_notes: Optional[str] = None
    owner_id: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MappingReview(BaseModel):
    id: str
    policy_id: str
    control_id: Optional[str] = None
    framework_id: Optional[str] = None
    evidence_snippet: Optional[str] = None
    confidence_score: Optional[float] = 0
    ai_rationale: Optional[str] = None
    decision: Optional[str] = None
    review_notes: Optional[str] = None
    reviewer_id: Optional[Any] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class Report(BaseModel):
    id: str
    policy_id: Optional[str] = None
    report_type: str
    format: str
    status: Optional[str] = None
    download_url: Optional[str] = None
    frameworks_included: Optional[List[str]] = None
    generated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuditLog(BaseModel):
    id: str
    actor_id: Optional[Any] = None
    action: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    details: Optional[Any] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class AIInsight(BaseModel):
    id: str
    policy_id: str
    insight_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    confidence: Optional[float] = 0
    status: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OTPVerifyRequest(BaseModel):
    email: str
    otp: str = Field(min_length=6, max_length=6)


class ResendOTPRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyResetOTPRequest(BaseModel):
    email: str
    otp: str = Field(min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _check_password_strength(v)


class AnalyzeRequest(BaseModel):
    policy_id: str
    frameworks: List[str]


class RunSimulationRequest(BaseModel):
    policy_id: str
    control_ids: Optional[List[str]] = None
    parameters: Optional[Any] = None


class GenerateReportRequest(BaseModel):
    policy_id: str
    report_type: str
    format: str
    frameworks_included: Optional[List[str]] = None

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: str
    password: str = Field(min_length=8, max_length=64)


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
    id: str
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
    framework_code: Optional[str] = None


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
    framework: str
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
    framework: Optional[str] = None
    control_id: Optional[str] = None
    control_name: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    remediation: Optional[str] = None
    owner: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MappingReview(BaseModel):
    id: str
    policy_id: str
    control_id: str
    framework: Optional[str] = None
    evidence_snippet: Optional[str] = None
    confidence_score: Optional[float] = 0
    ai_rationale: Optional[str] = None
    decision: Optional[str] = None
    review_notes: Optional[str] = None
    reviewer: Optional[str] = None
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
    actor: Optional[str] = None
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


class AnalyzeRequest(BaseModel):
    policy_id: str
    frameworks: List[str]


class RunSimulationRequest(BaseModel):
    policy_id: str
    parameters: Optional[Any] = None


class GenerateReportRequest(BaseModel):
    policy_id: str
    report_type: str
    format: str
    frameworks_included: Optional[List[str]] = None

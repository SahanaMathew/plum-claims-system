from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import uuid


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    PHARMACY_BILL = "PHARMACY_BILL"
    LAB_REPORT = "LAB_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    UNKNOWN = "UNKNOWN"


class DecisionType(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DocumentInput(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    actual_type: Optional[str] = None  # provided in test cases; real system would detect
    quality: Optional[str] = None      # GOOD, UNREADABLE, PARTIAL
    content: Optional[Dict[str, Any]] = None  # structured content (test cases provide this)
    patient_name_on_doc: Optional[str] = None


class ClaimSubmission(BaseModel):
    claim_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: str
    claimed_amount: float
    hospital_name: Optional[str] = None
    ytd_claims_amount: Optional[float] = 0
    claims_history: Optional[List[Dict[str, Any]]] = []
    documents: List[DocumentInput]
    simulate_component_failure: Optional[bool] = False


class TraceStep(BaseModel):
    agent: str
    status: str  # SUCCESS, FAILED, SKIPPED, EARLY_EXIT, FLAGGED, CLEAR, PARTIAL, COMPLETED_WITH_ISSUES
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    checks: Optional[List[Dict[str, Any]]] = []
    error: Optional[str] = None
    timestamp: Optional[str] = None


class ClaimDecision(BaseModel):
    claim_id: str
    member_id: str
    decision: Optional[DecisionType] = None
    approved_amount: Optional[float] = None
    claimed_amount: float
    confidence_score: Optional[float] = None
    rejection_reasons: Optional[List[str]] = []
    partial_items: Optional[List[Dict[str, Any]]] = []
    message: str
    trace: List[TraceStep] = []
    pipeline_status: str = "COMPLETE"  # COMPLETE, DEGRADED, EARLY_EXIT
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

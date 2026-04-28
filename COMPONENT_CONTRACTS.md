# Component Contracts
## Health Insurance Claims Processing System — Plum AI Engineer Assignment

This document defines the interface contract for every significant component in the system. Each contract is precise enough that another engineer could reimplement the component from scratch without reading its source code.

---

## 1. PolicyEngine

**File**: `backend/policy/engine.py`
**Purpose**: Loads `policy_terms.json` and exposes deterministic rule-evaluation methods. All agents that need policy data go through this class — no agent reads the JSON directly.

---

### `__init__(policy_file: str)`

Loads and parses the policy JSON at startup. Builds a member lookup dict keyed by `member_id`.

**Raises**: `FileNotFoundError` if the policy file does not exist. `json.JSONDecodeError` if the file is malformed.

---

### `get_member(member_id: str) -> dict | None`

| | |
|---|---|
| **Input** | `member_id`: string (e.g. `"EMP001"`) |
| **Output** | Full member dict from policy, or `None` if not found |
| **Errors** | None — returns `None` for unknown members |

**Output shape (when found):**
```json
{
  "member_id": "EMP001",
  "name": "Rajesh Kumar",
  "date_of_birth": "1985-03-15",
  "gender": "M",
  "relationship": "SELF",
  "join_date": "2024-04-01",
  "dependents": ["DEP001", "DEP002"]
}
```

---

### `get_document_requirements(claim_category: str) -> dict`

| | |
|---|---|
| **Input** | `claim_category`: one of `CONSULTATION`, `DIAGNOSTIC`, `PHARMACY`, `DENTAL`, `VISION`, `ALTERNATIVE_MEDICINE` |
| **Output** | Dict with `required` and `optional` lists of document type strings |
| **Errors** | Returns `{"required": [], "optional": []}` for unknown category (does not raise) |

**Output shape:**
```json
{
  "required": ["PRESCRIPTION", "HOSPITAL_BILL"],
  "optional": ["LAB_REPORT", "DIAGNOSTIC_REPORT"]
}
```

---

### `get_opd_category(claim_category: str) -> dict | None`

| | |
|---|---|
| **Input** | `claim_category`: string |
| **Output** | OPD category config dict from policy, or `None` for unknown category |

**Output shape:**
```json
{
  "sub_limit": 2000,
  "copay_percent": 10,
  "network_discount_percent": 20,
  "requires_prescription": true,
  "covered": true
}
```

---

### `is_network_hospital(hospital_name: str) -> bool`

| | |
|---|---|
| **Input** | `hospital_name`: string (may be partial name, e.g. `"Apollo Hospitals, Delhi"`) |
| **Output** | `True` if the name contains or is contained by any network hospital name (case-insensitive) |
| **Errors** | Returns `False` for empty or `None` input |

---

### `check_waiting_period(member: dict, diagnosis_text: str, treatment_date: str) -> dict`

| | |
|---|---|
| **Input** | `member`: member dict (must have `join_date`), `diagnosis_text`: lowercased combined diagnosis string, `treatment_date`: ISO date string `"YYYY-MM-DD"` |
| **Output** | Result dict |
| **Errors** | May raise `ValueError` if dates are malformed |

**Output shape (no violation):**
```json
{ "violated": false }
```

**Output shape (violation):**
```json
{
  "violated": true,
  "condition": "diabetes",
  "wait_days": 90,
  "eligible_from": "2024-11-29",
  "message": "Treatment for diabetes is within the 90-day waiting period (joined 2024-09-01). Eligible from 2024-11-29."
}
```

**Conditions matched** (keyword → waiting days from policy):

| Condition | Keywords | Wait days |
|---|---|---|
| `diabetes` | diabetes, diabetic, metformin, glimepiride, insulin | 90 |
| `hypertension` | hypertension, blood pressure, bp, amlodipine | 90 |
| `thyroid_disorders` | thyroid, hypothyroid, hyperthyroid | 90 |
| `joint_replacement` | joint replacement, knee replacement, hip replacement | 730 |
| `maternity` | maternity, pregnancy, prenatal, antenatal, obstetric | 270 |
| `mental_health` | mental health, depression, anxiety, psychiatric | 180 |
| `obesity_treatment` | obesity, bariatric, weight loss, bmi | 365 |
| `hernia` | hernia | 365 |
| `cataract` | cataract | 365 |
| *(initial)* | *(any treatment)* | 30 |

---

### `check_exclusions(diagnoses: list[str], line_items: list[dict]) -> dict`

| | |
|---|---|
| **Input** | `diagnoses`: list of diagnosis strings, `line_items`: list of `{description, amount}` dicts |
| **Output** | Result dict |
| **Errors** | None |

**Output shape:**
```json
{
  "excluded_items": [
    {
      "description": "Teeth Whitening",
      "amount": 4000,
      "exclusion_matched": "cosmetic or aesthetic procedures"
    }
  ],
  "diagnosis_exclusion": null,
  "reason": "Policy exclusion: cosmetic or aesthetic procedures"
}
```

- `excluded_items`: line items whose description matched an exclusion rule
- `diagnosis_exclusion`: the exclusion phrase that matched the diagnosis text (or `null`)
- `reason`: human-readable reason string (or `null` if nothing excluded)

**Matching logic**: Uses a curated keyword map per exclusion category, with fallback to phrase and word matching. When `diagnosis_exclusion` is non-null, the caller should treat the entire claim as excluded regardless of individual line items.

---

### `check_pre_auth(claim_category: str, amount: float, tests: list[str]) -> dict`

| | |
|---|---|
| **Input** | `claim_category`, `amount` in INR, `tests`: list of test name strings |
| **Output** | Result dict |
| **Errors** | None |

**Output shape (required):**
```json
{
  "required": true,
  "reason": "Pre-authorization is required for MRI Lumbar Spine when the claimed amount exceeds ₹10,000. The claimed amount of ₹15,000 requires prior approval."
}
```

**Output shape (not required):**
```json
{ "required": false }
```

Pre-auth is triggered when: category is `DIAGNOSTIC` AND any test name matches `MRI`, `CT Scan`, or `PET Scan` AND claimed amount > ₹10,000.

---

### `check_per_claim_limit(amount: float, category_config: dict | None) -> dict`

| | |
|---|---|
| **Input** | `amount`: post-exclusion approved amount in INR, `category_config`: OPD category dict (optional) |
| **Output** | Result dict |
| **Errors** | None |

**Output shape:**
```json
{ "exceeded": true, "limit": 10000 }
```

**Effective limit**: `max(global_per_claim_limit, category_sub_limit)`. If `category_config` is `None`, uses global limit only (₹5,000).

---

## 2. DocumentVerificationAgent

**File**: `backend/agents/document_verification.py`
**Purpose**: Gate-check all uploaded documents before any AI processing. Operates on pure logic — no LLM calls.

### `run(context: dict) -> dict`

| | |
|---|---|
| **Input** | `context` dict containing `claim` (ClaimSubmission) and `trace` (list) |
| **Output** | Updated context dict |
| **Errors** | Does not raise. All failures are captured as early exits. |

**Context mutations:**

On success (all checks pass):
```python
context["doc_verification"] = {"status": "PASSED"}
context["trace"].append(TraceStep(status="SUCCESS", ...))
```

On failure (any check fails):
```python
context["early_exit"] = True
context["early_exit_message"] = "<specific human-readable message>"
context["trace"].append(TraceStep(status="EARLY_EXIT", ...))
```

**Checks performed** (first failure stops further checking):

1. **Document type check**: Required types for the claim category must all be present in uploaded documents. If a required type is missing, `early_exit_message` names both what was uploaded and what is needed. A generic message ("document missing") is not acceptable.

2. **Readability check**: If any document has `quality == "UNREADABLE"`, `early_exit_message` identifies that file by name/id and asks for re-upload.

3. **Cross-patient check**: If any two documents carry different non-null `patient_name_on_doc` values, `early_exit_message` names both patients found on which documents.

**Example early exit messages:**

- Type mismatch: `"Document type mismatch: You uploaded PRESCRIPTION but a HOSPITAL_BILL is required for a CONSULTATION claim. Please replace the incorrect document(s) with the required type(s)."`
- Unreadable: `"The document 'blurry_bill.jpg' (type: PHARMACY_BILL) could not be read — the image is too blurry or unclear. Please re-upload a clear photo or scan of this document to proceed."`
- Cross-patient: `"Patient name mismatch across documents: prescription_rajesh.jpg: Rajesh Kumar; bill_arjun.jpg: Arjun Mehta. All documents in a single claim must belong to the same patient."`

---

## 3. ExtractionAgent

**File**: `backend/agents/extraction.py`
**Purpose**: Extract structured information from each document and synthesize across documents.

### `run(context: dict) -> dict`

| | |
|---|---|
| **Input** | Context with `claim`, `trace`. Skips immediately if `context["early_exit"]` is `True`. |
| **Output** | Updated context |
| **Errors** | Per-document errors are caught and stored in `extracted_data.extraction_errors`. Agent does not raise. |

**Context mutations:**
```python
context["extracted_data"] = {
    "documents": [
        {
            "file_id": "F007",
            "type": "PRESCRIPTION",
            "data": {
                "patient_name": "Rajesh Kumar",
                "doctor_name": "Dr. Arun Sharma",
                "doctor_registration": "KA/45678/2015",
                "date": "2024-11-01",
                "diagnosis": "Viral Fever",
                "medicines": ["Paracetamol 650mg", "Vitamin C 500mg"],
                "line_items": [],
                "total_amount": null,
                "extraction_method": "provided_content"
            }
        }
    ],
    "primary_patient_name": "Rajesh Kumar",
    "all_patient_names": ["Rajesh Kumar"],
    "diagnoses": ["Viral Fever"],
    "line_items": [
        {"description": "Consultation Fee", "amount": 1000},
        {"description": "CBC Test", "amount": 300}
    ],
    "hospital_name": "City Clinic, Bengaluru",
    "extraction_errors": []
}
```

**Extraction modes:**
- If `document.content` is set → use directly (`extraction_method: "provided_content"`)
- Otherwise → call LLM with `response_format: json_object` → parse result (`extraction_method: "llm"`)

**LLM prompt contract:**
System: "You are a medical document extraction AI specializing in Indian healthcare documents. Extract all available information and return as JSON with fields: `patient_name`, `doctor_name`, `doctor_registration`, `date`, `diagnosis`, `treatment`, `medicines` (list), `test_names` (list), `line_items` (list of `{description, amount}`), `total_amount`, `hospital_name`, `notes`. Use null for missing fields."

---

## 4. PolicyCheckAgent

**File**: `backend/agents/policy_check.py`
**Purpose**: Apply every rule from the policy file to the extracted claim data and compute the approved amount.

### `run(context: dict) -> dict`

| | |
|---|---|
| **Input** | Context with `claim`, `extracted_data`, `trace`. Skips if `early_exit`. |
| **Output** | Updated context |
| **Errors** | Does not raise. Policy engine errors bubble up to the orchestrator. |

**Context mutations:**
```python
context["policy_result"] = {
    "checks": [
        {"check": "member_validation", "status": "PASSED", "detail": "..."},
        {"check": "exclusions", "status": "PASSED", "detail": "..."},
        {"check": "waiting_period", "status": "FAILED", "detail": "..."},
        {"check": "pre_authorization", "status": "PASSED", "detail": "..."},
        {"check": "per_claim_limit", "status": "PASSED", "detail": "..."},
        {"check": "network_discount", "status": "APPLIED", "detail": "..."},
        {"check": "copay", "status": "APPLIED", "detail": "..."}
    ],
    "rejection_reasons": ["WAITING_PERIOD"],
    "approved_amount": 0.0,
    "partial_items": [],
    "financial_breakdown": {
        "network_discount": {
            "applied": true, "hospital": "Apollo Hospitals",
            "discount_percent": 20, "before": 4500.0, "after": 3600.0
        },
        "copay": {"percent": 10, "amount": 360.0, "before": 3600.0, "after": 3240.0}
    }
}
```

**Possible rejection_reasons values:**
- `MEMBER_NOT_FOUND`
- `EXCLUDED_CONDITION` — diagnosis is on the policy exclusion list (hard stop, skips remaining checks)
- `PARTIAL_EXCLUSION` — some line items excluded, rest approved
- `WAITING_PERIOD`
- `PRE_AUTH_MISSING`
- `PER_CLAIM_EXCEEDED`

**Financial calculation order** (must be respected):
1. Start with `claimed_amount`
2. Subtract excluded line items (if `PARTIAL_EXCLUSION`)
3. Apply network discount on the remaining amount
4. Apply co-pay on the discounted amount

Network discount and co-pay are only applied when no hard rejection reason is present.

**Special case — EXCLUDED_CONDITION hard stop:**
When the diagnosis itself matches an exclusion, the agent short-circuits: sets `approved_amount=0`, marks all line items as excluded, writes the `policy_result` to context, appends the trace step, and returns immediately without running further checks.

---

## 5. FraudDetectionAgent

**File**: `backend/agents/fraud_detection.py`
**Purpose**: Compute a fraud score from claim patterns and set `requires_manual_review` when the threshold is exceeded.

### `run(context: dict) -> dict`

| | |
|---|---|
| **Input** | Context with `claim` (must include `claims_history` and `treatment_date`), `trace`. Skips if `early_exit`. |
| **Output** | Updated context |
| **Errors** | Does not raise |

**Context mutations:**
```python
context["fraud_result"] = {
    "fraud_score": 0.85,
    "signals": [
        {
            "signal": "EXCESSIVE_SAME_DAY_CLAIMS",
            "detail": "Member has 3 existing claims on 2024-10-30 (limit: 2). This is claim #4 on the same day.",
            "previous_claims": [{"claim_id": "CLM_0081", "date": "2024-10-30", ...}]
        }
    ],
    "requires_manual_review": true,
    "checks": [
        {"check": "same_day_claims", "status": "FLAGGED", "detail": "...", "count": 3},
        {"check": "high_value", "status": "PASSED", "detail": "..."}
    ]
}
```

**Signal scoring:**

| Signal | Condition | Score contribution |
|---|---|---|
| `EXCESSIVE_SAME_DAY_CLAIMS` | `len(same_day_history) >= same_day_claims_limit` | +0.85 |
| `HIGH_VALUE_CLAIM` | `claimed_amount >= high_value_claim_threshold` (₹25,000) | +0.30 |

`fraud_score` is capped at 1.0. `requires_manual_review = fraud_score >= 0.80`.

---

## 6. DecisionAgent

**File**: `backend/agents/decision.py`
**Purpose**: Synthesize all upstream results into a single explainable decision.

### `run(context: dict) -> dict`

| | |
|---|---|
| **Input** | Context with `policy_result`, `fraud_result`, `extracted_data`, `claim`, `trace`. Skips if `early_exit`. |
| **Output** | Updated context |
| **Errors** | Does not raise |

**Context mutations:**
```python
context["final_decision"] = {
    "decision": "APPROVED",           # APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW
    "approved_amount": 3240.0,
    "confidence_score": 0.95,
    "rejection_reasons": [],
    "partial_items": [],
    "message": "Claim approved for ₹3,240.00. Network discount 20% applied. Co-pay 10% deducted: ₹360.00."
}
```

**Decision priority (evaluated top-down, first match wins):**

1. `fraud_result.requires_manual_review == True` → `MANUAL_REVIEW`
   - `approved_amount = None`
   - Message lists all fraud signal details
2. `rejection_reasons` has any hard reason (not `PARTIAL_EXCLUSION`) → `REJECTED`
   - `approved_amount = 0`
   - Message concatenates the `detail` text of every FAILED policy check
3. `PARTIAL_EXCLUSION` in `rejection_reasons` → `PARTIAL`
   - `approved_amount` = post-exclusion approved amount
   - Message itemizes each line item with APPROVED/EXCLUDED status and reason
4. None of the above → `APPROVED`
   - Message includes financial breakdown (discount, co-pay)

**Confidence calculation:**

```
confidence = 1.0
- 0.10  per document in extracted_data.extraction_errors
- 0.25  if context["component_failed"] == True
- 0.10  per fraud signal (only when not routing to MANUAL_REVIEW)
floor:  0.10
```

When `component_failed`, confidence is additionally capped at 0.65 and the message appends: `"Note: One or more pipeline components failed during processing. Manual review is recommended."`

---

## 7. ClaimsPipeline (Orchestrator)

**File**: `backend/pipeline/orchestrator.py`
**Purpose**: Execute the agent pipeline, handle all exceptions, and produce the final `ClaimDecision`.

### `process(claim: ClaimSubmission) -> ClaimDecision`

| | |
|---|---|
| **Input** | `ClaimSubmission` Pydantic model |
| **Output** | `ClaimDecision` Pydantic model |
| **Errors** | Does not raise. All agent exceptions are caught internally. |

**Execution order:**
1. `DocumentVerificationAgent` — may set `early_exit`
2. `ExtractionAgent`
3. `PolicyCheckAgent`
4. `FraudDetectionAgent`
5. `DecisionAgent`

**Error handling per agent:**
- Each agent is executed inside `try/except Exception`
- On exception: `context["component_failed"] = True`, a FAILED `TraceStep` is appended, execution continues with the next agent
- If `context["early_exit"]` is `True` after any agent, the loop breaks immediately

**Output mapping:**

On early exit:
```python
ClaimDecision(
    decision=None,
    approved_amount=None,
    confidence_score=None,
    message=context["early_exit_message"],
    pipeline_status="EARLY_EXIT",
    trace=context["trace"]
)
```

On normal completion:
```python
ClaimDecision(
    decision=final_decision["decision"],
    approved_amount=final_decision["approved_amount"],
    confidence_score=final_decision["confidence_score"],
    rejection_reasons=final_decision["rejection_reasons"],
    partial_items=final_decision["partial_items"],
    message=final_decision["message"],
    pipeline_status="DEGRADED" if component_failed else "COMPLETE",
    trace=context["trace"]
)
```

---

## 8. REST API

**File**: `backend/main.py`

### `POST /api/submit-claim`

| | |
|---|---|
| **Request body** | `ClaimSubmission` JSON |
| **Response** | `ClaimDecision` JSON |
| **Status codes** | 200 OK, 422 Unprocessable Entity (validation error), 500 Internal Server Error |

**ClaimSubmission schema:**
```json
{
  "member_id": "EMP001",
  "policy_id": "PLUM_GHI_2024",
  "claim_category": "CONSULTATION",
  "treatment_date": "2024-11-01",
  "claimed_amount": 1500,
  "hospital_name": "Apollo Hospitals",
  "ytd_claims_amount": 5000,
  "claims_history": [],
  "documents": [
    {
      "file_id": "F007",
      "file_name": "prescription.jpg",
      "actual_type": "PRESCRIPTION",
      "quality": "GOOD",
      "content": { "patient_name": "...", "diagnosis": "..." },
      "patient_name_on_doc": "Rajesh Kumar"
    }
  ],
  "simulate_component_failure": false
}
```

**ClaimDecision schema:**
```json
{
  "claim_id": "A1B2C3D4",
  "member_id": "EMP001",
  "decision": "APPROVED",
  "approved_amount": 1350.0,
  "claimed_amount": 1500.0,
  "confidence_score": 1.0,
  "rejection_reasons": [],
  "partial_items": [],
  "message": "Claim approved for ₹1,350.00. Co-pay 10% deducted: ₹150.00.",
  "trace": [
    {
      "agent": "DocumentVerificationAgent",
      "status": "SUCCESS",
      "input_summary": "Uploaded: ['PRESCRIPTION', 'HOSPITAL_BILL'], Required: ['PRESCRIPTION', 'HOSPITAL_BILL']",
      "output_summary": "All document checks passed",
      "checks": [{"check": "all_document_checks", "status": "PASSED", "detail": "..."}],
      "error": null,
      "timestamp": "2024-11-01T10:30:00.000Z"
    }
  ],
  "pipeline_status": "COMPLETE",
  "created_at": "2024-11-01T10:30:00.000Z"
}
```

---

### `GET /api/claim/{claim_id}`

| | |
|---|---|
| **Path param** | `claim_id`: string |
| **Response** | `ClaimDecision` JSON |
| **Status codes** | 200 OK, 404 Not Found |

---

### `GET /api/claims`

| | |
|---|---|
| **Response** | Array of all `ClaimDecision` objects processed since server start |
| **Status codes** | 200 OK |

---

### `GET /api/test-cases`

| | |
|---|---|
| **Response** | Contents of `test_cases.json` |
| **Status codes** | 200 OK |

---

### `GET /api/health`

| | |
|---|---|
| **Response** | `{"status": "ok"}` |
| **Status codes** | 200 OK |

---

## 9. Data Models

**File**: `backend/models/schemas.py`

### ClaimCategory (enum)
`CONSULTATION | DIAGNOSTIC | PHARMACY | DENTAL | VISION | ALTERNATIVE_MEDICINE`

### DocumentType (enum)
`PRESCRIPTION | HOSPITAL_BILL | PHARMACY_BILL | LAB_REPORT | DISCHARGE_SUMMARY | DENTAL_REPORT | DIAGNOSTIC_REPORT | UNKNOWN`

### DecisionType (enum)
`APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW`

### pipeline_status (string enum, not Pydantic)
`COMPLETE | DEGRADED | EARLY_EXIT`

### TraceStep
```python
agent: str                          # agent name
status: str                         # SUCCESS | FAILED | EARLY_EXIT | FLAGGED | CLEAR | ...
input_summary: str | None
output_summary: str | None
checks: list[dict]                  # [{check, status, detail, ...}]
error: str | None                   # exception message if agent failed
timestamp: str                      # UTC ISO 8601
```

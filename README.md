# Plum Health Insurance Claims Processing System

An AI-powered, multi-agent claims processing system for the Plum AI Engineer assignment. Automates the full decision pipeline — document verification, data extraction, policy evaluation, fraud detection, and final decision synthesis — with a complete audit trace on every claim.

---

## Quick Start

### Prerequisites
- Python 3.10+
- A [Groq API key](https://console.groq.com) (free tier)

### Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/plum-claims-system.git
cd plum-claims-system/claims-system

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and set GROQ_API_KEY=<your-key>

# 4. Run the server
python run.py
```

Open **http://localhost:8000** in your browser. The UI loads immediately.

---

## Project Structure

```
claims-system/
├── backend/
│   ├── agents/
│   │   ├── base.py                  # BaseAgent: LLM calling + trace helpers
│   │   ├── document_verification.py # Gate check before any AI processing
│   │   ├── extraction.py            # LLM-powered structured extraction
│   │   ├── policy_check.py          # Deterministic policy rule evaluation
│   │   ├── fraud_detection.py       # Pattern-based fraud scoring
│   │   └── decision.py              # Final decision synthesis
│   ├── pipeline/
│   │   └── orchestrator.py          # Agent execution loop + error handling
│   ├── policy/
│   │   └── engine.py                # Stateless rule engine over policy_terms.json
│   ├── models/
│   │   └── schemas.py               # Pydantic request/response models
│   ├── api/
│   │   └── routes.py                # REST endpoints
│   └── main.py                      # FastAPI app setup
├── frontend/
│   ├── index.html                   # Single-page application
│   ├── app.js                       # DOM + API integration
│   └── style.css
├── tests/
│   └── test_cases_runner.py         # pytest runner for 12 test cases
├── policy_terms.json                # All policy rules (coverage, limits, exclusions)
├── test_cases.json                  # 12 evaluation scenarios
├── run.py                           # Server entry point
├── run_eval.py                      # Evaluation script
├── ARCHITECTURE.docx                # Architecture document (Word)
├── COMPONENT_CONTRACTS.docx         # Component contracts (Word)
├── EVAL_REPORT.docx                 # Evaluation report (Word)
├── ARCHITECTURE.md                  # Architecture document (Markdown)
├── COMPONENT_CONTRACTS.md           # Component contracts (Markdown)
├── EVAL_REPORT.md                   # Evaluation report (Markdown)
└── eval_report.json                 # Machine-readable eval results
```

---

## System Architecture

The system is a **sequential multi-agent pipeline** backed by a FastAPI server.

```
Claim Submission
      │
      ▼
1. DocumentVerificationAgent  ← pure logic, no LLM
      │  (early exit on bad docs)
      ▼
2. ExtractionAgent            ← Groq llama-3.3-70b-versatile
      │
      ▼
3. PolicyCheckAgent           ← deterministic rules from policy_terms.json
      │
      ▼
4. FraudDetectionAgent        ← pattern scoring
      │
      ▼
5. DecisionAgent              ← synthesizes final decision + confidence
      │
      ▼
ClaimDecision (+ full audit trace)
```

### Key Design Principles

| Principle | Implementation |
|---|---|
| **LLM only where needed** | Extraction only; all policy rules are deterministic Python |
| **Never crash** | Every agent wrapped in try/except; pipeline continues in degraded mode |
| **Full observability** | Every check in every agent is logged to the trace |
| **Data-driven policy** | Changing rules requires editing `policy_terms.json`, not code |
| **Specific error messages** | Early exits name the exact problem (file name, document type, patient names) |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/submit-claim` | Process a claim; returns `ClaimDecision` with full trace |
| `GET` | `/api/claim/{claim_id}` | Retrieve a stored decision |
| `GET` | `/api/claims` | List all processed claims |
| `GET` | `/api/test-cases` | Return `test_cases.json` for the UI |
| `GET` | `/api/health` | Health check |

### Example Request

```json
POST /api/submit-claim
{
  "member_id": "EMP001",
  "policy_id": "PLUM_GHI_2024",
  "claim_category": "CONSULTATION",
  "treatment_date": "2024-11-01",
  "claimed_amount": 1500,
  "hospital_name": "Apollo Hospitals",
  "claims_history": [],
  "documents": [
    {
      "file_id": "F001",
      "file_name": "prescription.jpg",
      "actual_type": "PRESCRIPTION",
      "quality": "GOOD",
      "content": {
        "patient_name": "Rajesh Kumar",
        "diagnosis": "Viral Fever",
        "medicines": ["Paracetamol 650mg"]
      },
      "patient_name_on_doc": "Rajesh Kumar"
    }
  ]
}
```

### Example Response

```json
{
  "claim_id": "A1B2C3D4",
  "decision": "APPROVED",
  "approved_amount": 1350.0,
  "claimed_amount": 1500.0,
  "confidence_score": 1.0,
  "message": "Claim approved for Rs 1,350.00. Co-pay 10% deducted: Rs 150.00.",
  "pipeline_status": "COMPLETE",
  "trace": [
    {
      "agent": "DocumentVerificationAgent",
      "status": "SUCCESS",
      "checks": [{"check": "all_document_checks", "status": "PASSED", "detail": "..."}]
    },
    {
      "agent": "PolicyCheckAgent",
      "status": "SUCCESS",
      "checks": [
        {"check": "member_validation", "status": "PASSED", "detail": "Rajesh Kumar found"},
        {"check": "copay", "status": "APPLIED", "detail": "Co-pay 10%: Rs 150. Final: Rs 1,350."}
      ]
    }
  ]
}
```

---

## Decision Types

| Decision | When |
|---|---|
| `APPROVED` | All policy checks pass; financial amounts calculated |
| `PARTIAL` | Some line items excluded, rest approved; itemized breakdown returned |
| `REJECTED` | Hard policy violation (waiting period, exclusion, limit, missing pre-auth) |
| `MANUAL_REVIEW` | Fraud score ≥ 0.80; never auto-rejected |
| `null` (EARLY_EXIT) | Document problem caught before any processing |

---

## Running the Evaluation

```bash
# Run all 12 test cases and print results
python run_eval.py

# Or with pytest
pytest tests/test_cases_runner.py -v
```

**Results: 12 / 12 pass (100%)** — see `EVAL_REPORT.md` or `EVAL_REPORT.docx` for full trace of every case.

---

## Deliverables

| File | Description |
|---|---|
| `ARCHITECTURE.docx` / `.md` | System design, component breakdown, trade-offs, scaling plan |
| `COMPONENT_CONTRACTS.docx` / `.md` | Interface contracts for every significant component |
| `EVAL_REPORT.docx` / `.md` | Full trace + verdict for all 12 test cases |
| `eval_report.json` | Machine-readable evaluation results |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API server | FastAPI + Uvicorn |
| LLM | Groq API (`llama-3.3-70b-versatile`) |
| Data validation | Pydantic v2 |
| Frontend | Vanilla HTML / JS / CSS |
| Tests | pytest |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key for LLM extraction |
| `PORT` | No | Server port (default: 8000) |

---

## Deployment

The app includes a `Procfile` for Heroku:

```bash
heroku create
heroku config:set GROQ_API_KEY=<your-key>
git push heroku main
```

---

## Limitations & Future Work

- **Storage**: In-memory; restart clears all claims. Production needs PostgreSQL.
- **Document OCR**: Test mode uses structured `content` fields. Production needs a vision-capable model for raw images.
- **Authentication**: No auth middleware. Production needs member tokens or internal service auth.
- **Async agents**: Current agents are synchronous. High concurrency requires `AsyncGroq` + `async/await`.
- **Monthly claims limit**: Policy defines `monthly_claims_limit: 6` but enforcement needs a claims DB.

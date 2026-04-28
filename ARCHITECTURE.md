# Architecture Document
## Health Insurance Claims Processing System — Plum AI Engineer Assignment

---

## 1. Problem Framing

Manual claims processing at Plum is slow, inconsistent, and does not scale. The goal is to automate the decision-making pipeline so that routine claims are resolved instantly, edge cases are surfaced with full context, and every decision can be explained and audited.

The design must handle three categories of failure gracefully:
- **Bad input** (wrong documents, unreadable files, mismatched patients) — caught early, before any AI processing
- **Policy violations** (waiting periods, exclusions, limits) — caught deterministically from the policy file
- **Infrastructure failures** (LLM timeout, parsing error) — caught at the agent level, pipeline continues in degraded mode

---

## 2. High-Level Architecture

```
                        ┌─────────────────────────────────┐
                        │         FastAPI Backend          │
                        │                                  │
  HTTP POST ──────────► │  /api/submit-claim               │
  ClaimSubmission        │         │                        │
                        │         ▼                        │
                        │   ClaimsPipeline.process()       │
                        │         │                        │
                        │  ┌──────▼──────────────────┐    │
                        │  │  Multi-Agent Pipeline    │    │
                        │  │                          │    │
                        │  │  1. DocumentVerification │    │
                        │  │         │                │    │
                        │  │         ▼                │    │
                        │  │  2. Extraction           │    │
                        │  │         │                │    │
                        │  │         ▼                │    │
                        │  │  3. PolicyCheck          │    │
                        │  │         │                │    │
                        │  │         ▼                │    │
                        │  │  4. FraudDetection       │    │
                        │  │         │                │    │
                        │  │         ▼                │    │
                        │  │  5. Decision             │    │
                        │  └──────────────────────────┘    │
                        │         │                        │
                        │         ▼                        │
  HTTP Response ◄────── │   ClaimDecision (+ full trace)   │
                        └─────────────────────────────────┘
                                  ▲
                        ┌─────────┴────────┐
                        │  PolicyEngine    │
                        │  (policy_terms   │
                        │   .json)         │
                        └──────────────────┘
```

The frontend is a plain HTML/JS single-page application served by the same FastAPI process. It communicates with the backend via the REST API.

---

## 3. Component Breakdown

### 3.1 ClaimsPipeline (Orchestrator)

The pipeline is a **sequential multi-agent system**. Each agent receives a shared mutable `context` dict, enriches it, and passes it to the next agent. The orchestrator owns the execution loop and all error handling.

**Key design decisions:**

- **Sequential over parallel**: Agents are ordered by dependency — extraction must precede policy check; policy check must precede decision. There is no benefit to parallelism here.
- **Shared context object**: Agents communicate through a single dict rather than typed message passing. This trades some type safety for simplicity and makes the full pipeline state inspectable at any point.
- **Catch-and-continue**: Each agent is wrapped in a try/except. If an agent throws, the pipeline marks `component_failed=True`, appends a FAILED trace step, and continues. This ensures the system never returns a 500 on a recoverable failure.
- **Early exit**: The DocumentVerificationAgent can set `early_exit=True`, which causes the orchestrator to stop the pipeline and return immediately. This avoids wasting LLM tokens on a claim with fundamentally broken documents.

### 3.2 DocumentVerificationAgent

**Purpose**: Catch document problems before any AI processing.

**Checks performed** (in order):
1. **Type check** — required document types for the claim category are loaded from `policy_terms.json`. If a required type is missing or the wrong type was uploaded, the agent exits with a specific message naming the uploaded type and the required type.
2. **Readability check** — if any document has `quality == "UNREADABLE"`, the agent exits with a message identifying that specific file and asking for a re-upload.
3. **Cross-patient check** — if documents carry `patient_name_on_doc` fields that differ from each other, the agent exits with a message naming both patients found.

**Why pure logic, no LLM**: Document type verification is a deterministic lookup against a policy table. Using an LLM here would be slower, more expensive, and less reliable than a direct comparison. The LLM's job is pattern recognition in unstructured text — not table lookups.

### 3.3 ExtractionAgent

**Purpose**: Extract structured data from each uploaded document.

**Two modes:**
- **Test case mode** (document has a `content` field): data is used directly, no LLM call made. This enables fast, deterministic testing.
- **Production mode** (raw file): the document is described to the LLM (Groq / `llama-3.3-70b-versatile`) which returns a structured JSON with fields: `patient_name`, `doctor_name`, `doctor_registration`, `date`, `diagnosis`, `medicines`, `test_names`, `line_items`, `total_amount`, `hospital_name`.

After per-document extraction, the agent synthesizes across documents to produce a unified `extracted_data` object: primary patient name, all diagnoses, all line items, hospital name.

Partial extraction failures are captured and propagated — if one document fails to parse, the agent continues with the others and logs the error.

### 3.4 PolicyCheckAgent

**Purpose**: Apply every rule from `policy_terms.json` deterministically.

**Checks performed** (in order):
1. **Member validation** — member must exist in the policy roster
2. **Exclusions** — checked BEFORE waiting periods; an excluded diagnosis is a hard stop (EXCLUDED_CONDITION). Line-item exclusions produce PARTIAL decisions.
3. **Waiting period** — condition-specific waiting periods matched via keyword map against extracted diagnosis text
4. **Pre-authorization** — required for high-value diagnostic tests (MRI, CT, PET > ₹10,000)
5. **Per-claim limit** — checked against post-exclusion approved amount; uses category sub-limit when higher than global per-claim limit
6. **Network discount + co-pay** — applied only when no hard rejection exists; network discount applied first, then co-pay on the discounted amount

**Why exclusions before waiting periods**: An excluded condition (e.g. bariatric surgery) is a permanent policy exclusion, not a time-limited restriction. Checking it first avoids misleading the member into thinking re-submission after a waiting period would succeed.

**Why use category sub-limit for per-claim check**: The global `per_claim_limit` (₹5,000) is a floor for consultation-type claims. Categories like dental (sub-limit ₹10,000) and diagnostic have higher category-specific caps. The effective limit is `max(global_limit, category_sub_limit)`.

### 3.5 FraudDetectionAgent

**Purpose**: Detect unusual patterns that warrant human review rather than auto-decision.

**Signals checked:**
1. **Same-day claim excess** — if the member has already submitted ≥ `same_day_claims_limit` claims on the treatment date, fraud score += 0.85 (immediately triggers MANUAL_REVIEW threshold)
2. **High-value claim** — if the claimed amount exceeds ₹25,000, fraud score += 0.30

`requires_manual_review` is set when `fraud_score >= fraud_score_manual_review_threshold` (0.80 from policy). When set, the DecisionAgent outputs MANUAL_REVIEW regardless of policy check results.

**Why not auto-reject fraud**: Auto-rejection of suspected fraud is legally and operationally risky. A human review is the correct response — the fraud signal must be visible in the trace with the specific triggers listed.

### 3.6 DecisionAgent

**Purpose**: Synthesize all upstream results into a final, explainable decision.

**Decision priority order:**
1. If `fraud_result.requires_manual_review` → `MANUAL_REVIEW`
2. If `rejection_reasons` contains hard failures → `REJECTED`
3. If `PARTIAL_EXCLUSION` in rejection reasons → `PARTIAL` with itemized breakdown
4. Otherwise → `APPROVED` with financial breakdown (discount, co-pay)

**Confidence calculation:**
- Starts at 1.0
- `-0.10` per document extraction error
- `-0.25` if any pipeline component failed (degraded mode)
- `-0.10` per fraud signal present (when not routing to MANUAL_REVIEW)
- Floor: 0.10

**Why a separate DecisionAgent**: Separating synthesis from checking means the decision logic is testable in isolation. It also means the decision explanation is generated in one place, making it easy to audit and extend.

### 3.7 PolicyEngine

**Purpose**: Stateless rule engine that loads and interprets `policy_terms.json`.

All policy logic is data-driven — nothing is hardcoded in the agents. The engine exposes methods like `check_waiting_period`, `check_exclusions`, `check_pre_auth`, `check_per_claim_limit`, and `is_network_hospital`. Changing policy rules requires only updating the JSON, not the code.

---

## 4. Data Flow

```
ClaimSubmission
    │
    ├─ member_id, policy_id, claim_category
    ├─ treatment_date, claimed_amount
    ├─ hospital_name (optional)
    ├─ claims_history (for fraud check)
    └─ documents[]
           ├─ file_id, file_name
           ├─ actual_type (PRESCRIPTION, HOSPITAL_BILL, etc.)
           ├─ quality (GOOD, UNREADABLE)
           ├─ content (structured dict, test mode)
           └─ patient_name_on_doc (for cross-patient check)

    ▼ DocumentVerificationAgent
context["doc_verification"] = {status: PASSED}
  OR
context["early_exit"] = True
context["early_exit_message"] = "specific error..."

    ▼ ExtractionAgent
context["extracted_data"] = {
    documents: [{file_id, type, data: {...}}],
    primary_patient_name, diagnoses[], line_items[],
    hospital_name, extraction_errors[]
}

    ▼ PolicyCheckAgent
context["policy_result"] = {
    checks: [{check, status, detail}...],
    rejection_reasons: [],
    approved_amount: float,
    partial_items: [{description, amount, status, reason}...],
    financial_breakdown: {network_discount, copay}
}

    ▼ FraudDetectionAgent
context["fraud_result"] = {
    fraud_score: float,
    signals: [{signal, detail}...],
    requires_manual_review: bool,
    checks: [...]
}

    ▼ DecisionAgent
context["final_decision"] = {
    decision: APPROVED|PARTIAL|REJECTED|MANUAL_REVIEW,
    approved_amount: float,
    confidence_score: float,
    rejection_reasons: [],
    partial_items: [],
    message: str
}

    ▼ ClaimsPipeline
ClaimDecision (+ trace[] with every agent's steps)
```

---

## 5. Observability

Every agent appends a `TraceStep` to `context["trace"]`. A trace step contains:
- `agent`: which agent produced it
- `status`: SUCCESS / FAILED / EARLY_EXIT / FLAGGED / CLEAR / COMPLETED_WITH_ISSUES
- `input_summary`: what the agent was given
- `output_summary`: what it concluded
- `checks`: list of individual checks with their pass/fail status and detail text
- `error`: exception message if the agent failed
- `timestamp`: UTC ISO timestamp

The full trace is returned on every `ClaimDecision` response. An operations team member can read the trace top-to-bottom and reconstruct exactly:
- What documents were verified and what issues were found
- What was extracted from each document
- Which policy rules were checked, which passed, which failed and why
- What fraud signals were evaluated
- How the final amount was calculated (discount → co-pay)

**Example trace for TC010 (network discount + co-pay):**
```
DocumentVerificationAgent: SUCCESS — uploaded PRESCRIPTION, HOSPITAL_BILL match required
ExtractionAgent: SUCCESS — patient Deepak Shah, diagnosis Acute Bronchitis, ₹4,500 total
PolicyCheckAgent: SUCCESS
  ✓ member_validation: EMP010 found
  ✓ exclusions: none
  ✓ waiting_period: none
  ✓ pre_authorization: not required
  ✓ per_claim_limit: ₹4,500 within limit
  ✓ network_discount: Apollo Hospitals 20% → ₹4,500 → ₹3,600
  ✓ copay: 10% → ₹360 deducted → ₹3,240
FraudDetectionAgent: CLEAR — score 0.00
DecisionAgent: SUCCESS — APPROVED ₹3,240, confidence 1.0
```

---

## 6. Error Handling Strategy

| Failure Type | Behaviour |
|---|---|
| Wrong document type | Early exit before any processing; specific message to member |
| Unreadable document | Early exit; ask member to re-upload that specific file |
| Cross-patient documents | Early exit; names both patients found |
| Extraction LLM error | Log error in trace, continue with partial data; confidence reduced |
| Policy engine exception | Caught by orchestrator; `component_failed=True`; pipeline continues |
| Any agent unhandled exception | Caught by orchestrator; FAILED trace step added; pipeline continues |
| Degraded pipeline decision | Decision includes note recommending manual review; confidence capped at 0.65 |

The system will never return an HTTP 500 for a recoverable claim processing failure. It returns a `ClaimDecision` with `pipeline_status=DEGRADED` and reduced confidence instead.

---

## 7. Design Trade-offs

### What I chose and why

**Sequential agent pipeline over a graph-based DAG**
A DAG framework (like LangGraph) would be appropriate at higher complexity — but for 5 agents with a fixed dependency order, the added abstraction would obscure the control flow. The sequential loop with a shared context is readable and debuggable in one file.

**Deterministic policy engine, LLM only for extraction**
LLMs are used only where deterministic code cannot reasonably substitute — extracting structure from messy, unformatted documents. All rule evaluation (waiting periods, exclusions, limits, co-pays) is done in Python against the JSON policy file. This means policy decisions are reproducible, testable, and explainable without any LLM involvement.

**Groq (llama-3.3-70b-versatile) over GPT-4**
Free tier with generous rate limits. For structured extraction with a `response_format: json_object` constraint, Llama 3.3 70B performs comparably to GPT-4 at zero cost. The abstraction in `BaseAgent._call_llm` means the model can be swapped in `config.py`.

**In-memory claim store over a database**
For a 2-day assignment, a database adds setup friction with minimal benefit for demonstration. In production this would be replaced with PostgreSQL + a claims table.

**No async in agents**
The current agents are synchronous. For a production system processing concurrent claims, agents should be refactored to `async` with `await` for LLM calls (using `AsyncGroq`). The FastAPI layer already supports this.

### What I cut and why

**Real document OCR / vision**: The assignment specifies documents will be messy (handwritten, blurry). In production, documents would be passed as image bytes to a vision-capable model. In this implementation, documents in test mode carry pre-structured `content` fields, and production mode sends a text description to the LLM. I documented this assumption in the code.

**Persistent storage**: Claims are stored in-memory per process restart. An in-memory dict is sufficient for the demo and evaluation.

**Authentication**: No API key or auth middleware. In production, every endpoint would require a member token or internal service auth.

**Monthly claims limit check**: The policy specifies `monthly_claims_limit: 6` in fraud thresholds, but the test cases don't include a monthly-limit scenario and `claims_history` in test inputs only carries same-day history. This check would be added when a proper claims database is in place.

---

## 8. Scaling to 10x Load

At 10x volume (750,000+ claims/year, ~85/hour peak), the following changes are needed:

| Area | Change |
|---|---|
| **Concurrency** | Switch all agent LLM calls to `async` with `AsyncGroq`. FastAPI already handles async natively. |
| **Storage** | Replace in-memory store with PostgreSQL. Add a `claims` table with indexed `member_id`, `treatment_date`, `decision`. |
| **Queue** | Move claim processing off the HTTP request path. POST `/submit-claim` enqueues the job (Redis + Celery or AWS SQS), returns a `claim_id` immediately. Client polls `/claim/{id}`. |
| **LLM cost** | Route simple document types (printed bills with clear line items) to the smaller `llama-3.1-8b-instant` model. Reserve 70B only for complex extractions. |
| **Rate limiting** | Groq free tier has token limits. At scale, use a paid tier or self-host an open-weight model on GPU (vLLM). |
| **Policy engine** | The `PolicyEngine` is already stateless and reads config once at startup — it scales horizontally without changes. |
| **Observability** | Replace the in-trace logging with structured JSON logs shipped to a log aggregator (Datadog, Grafana Loki). Add a Prometheus metrics endpoint for decision rates, confidence distributions, and agent latencies. |

---

## 9. Technology Summary

| Component | Technology | Reason |
|---|---|---|
| API server | FastAPI + Uvicorn | Async-native, automatic OpenAPI docs, Pydantic validation |
| AI / LLM | Groq API (`llama-3.3-70b-versatile`) | Free tier, fast inference, OpenAI-compatible |
| Data validation | Pydantic v2 | Type-safe request/response models, automatic validation |
| Policy rules | JSON + Python (no ORM) | Policy is data, not code — easily updatable by non-engineers |
| Frontend | Vanilla HTML/JS/CSS | Zero build step, easy to demo locally and deploy anywhere |
| Tests | pytest | Simple, standard, runs without any external services |

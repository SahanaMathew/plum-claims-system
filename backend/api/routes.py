from fastapi import APIRouter, HTTPException
from backend.models.schemas import ClaimSubmission, ClaimDecision
from backend.pipeline.orchestrator import ClaimsPipeline
import json
import os

router = APIRouter()
pipeline = ClaimsPipeline()
claims_store: dict = {}


@router.post("/submit-claim", response_model=ClaimDecision)
def submit_claim(claim: ClaimSubmission):
    try:
        result = pipeline.process(claim)
        claims_store[result.claim_id] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/claim/{claim_id}", response_model=ClaimDecision)
def get_claim(claim_id: str):
    if claim_id not in claims_store:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claims_store[claim_id]


@router.get("/claims")
def list_claims():
    return list(claims_store.values())


@router.get("/test-cases")
def get_test_cases():
    tc_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "test_cases.json",
    )
    with open(tc_file) as f:
        return json.load(f)


@router.get("/health")
def health():
    return {"status": "ok"}

"""
Run all 12 test cases against the claims processing pipeline.
Usage: python -m pytest tests/test_cases_runner.py -v
"""
import json
import os
import sys
import pytest

# Allow running from the claims-system directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.pipeline.orchestrator import ClaimsPipeline
from backend.models.schemas import ClaimSubmission


POLICY_ID = "PLUM_GHI_2024"


def load_test_cases():
    tc_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "test_cases.json",
    )
    with open(tc_file) as f:
        return json.load(f)["test_cases"]


pipeline = ClaimsPipeline()


def run_test_case(tc: dict):
    inp = tc["input"]
    docs = []
    for d in inp.get("documents", []):
        docs.append(
            {
                "file_id": d.get("file_id", ""),
                "file_name": d.get("file_name"),
                "actual_type": d.get("actual_type"),
                "quality": d.get("quality"),
                "content": d.get("content"),
                "patient_name_on_doc": d.get("patient_name_on_doc"),
            }
        )

    claim = ClaimSubmission(
        member_id=inp["member_id"],
        policy_id=inp["policy_id"],
        claim_category=inp["claim_category"],
        treatment_date=inp["treatment_date"],
        claimed_amount=inp["claimed_amount"],
        hospital_name=inp.get("hospital_name"),
        ytd_claims_amount=inp.get("ytd_claims_amount", 0),
        claims_history=inp.get("claims_history", []),
        documents=docs,
        simulate_component_failure=inp.get("simulate_component_failure", False),
    )

    result = pipeline.process(claim)
    return result


test_cases_data = load_test_cases()


@pytest.mark.parametrize(
    "tc",
    test_cases_data,
    ids=[tc["case_id"] for tc in test_cases_data],
)
def test_claim_case(tc):
    result = run_test_case(tc)
    expected = tc["expected"]

    print(f"\n{'=' * 60}")
    print(f"Case: {tc['case_id']} — {tc['case_name']}")
    print(f"Decision:        {result.decision}")
    print(f"Pipeline status: {result.pipeline_status}")
    print(f"Approved amount: {result.approved_amount}")
    print(f"Confidence:      {result.confidence_score}")
    print(f"Message: {result.message[:300]}")
    if result.rejection_reasons:
        print(f"Rejection reasons: {result.rejection_reasons}")
    if result.partial_items:
        print(f"Partial items: {result.partial_items}")
    print()

    if expected.get("decision") is None:
        # Early exit expected (TC001, TC002, TC003)
        assert result.pipeline_status == "EARLY_EXIT", (
            f"Expected EARLY_EXIT but got pipeline_status={result.pipeline_status}, "
            f"decision={result.decision}"
        )
        print("PASS - Early exit detected correctly")
    else:
        expected_decision = expected.get("decision")
        if expected_decision:
            assert result.decision == expected_decision, (
                f"Expected decision={expected_decision} but got {result.decision}"
            )

        # Check approved amount within ±1 rupee tolerance
        if expected.get("approved_amount") is not None:
            assert result.approved_amount is not None, (
                f"Expected approved_amount={expected['approved_amount']} but got None"
            )
            assert abs(result.approved_amount - expected["approved_amount"]) < 1, (
                f"Expected approved_amount=Rs {expected['approved_amount']} "
                f"but got Rs {result.approved_amount}"
            )

        # Check rejection reasons if specified
        if expected.get("rejection_reasons"):
            for reason in expected["rejection_reasons"]:
                assert reason in (result.rejection_reasons or []), (
                    f"Expected rejection reason '{reason}' not found in {result.rejection_reasons}"
                )

        # TC011 — component failure
        if tc["case_id"] == "TC011":
            assert result.pipeline_status in ("DEGRADED", "COMPLETE"), (
                f"Expected DEGRADED pipeline status but got {result.pipeline_status}"
            )
            assert result.confidence_score is not None
            # Confidence must be lower than normal (which would be 1.0)
            assert result.confidence_score < 1.0, (
                f"Expected confidence < 1.0 for degraded pipeline, got {result.confidence_score}"
            )
            assert "manual review" in result.message.lower() or "component" in result.message.lower(), (
                f"Expected failure note in message but got: {result.message}"
            )

        print(f"PASS")

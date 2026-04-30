"""
Standalone eval runner — outputs full results for all 12 test cases to eval_report.json
and prints a human-readable summary.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.pipeline.orchestrator import ClaimsPipeline
from backend.models.schemas import ClaimSubmission

POLICY_ID = "PLUM_GHI_2024"


def load_test_cases():
    tc_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_cases.json")
    with open(tc_file, encoding="utf-8") as f:
        return json.load(f)["test_cases"]


def run_case(tc, pipeline):
    inp = tc["input"]
    docs = [
        {
            "file_id": d.get("file_id", ""),
            "file_name": d.get("file_name"),
            "actual_type": d.get("actual_type"),
            "quality": d.get("quality"),
            "content": d.get("content"),
            "patient_name_on_doc": d.get("patient_name_on_doc"),
        }
        for d in inp.get("documents", [])
    ]
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
    return pipeline.process(claim)


def check_pass(result, expected):
    """Return (passed: bool, reason: str)"""
    if expected.get("decision") is None:
        if result.pipeline_status == "EARLY_EXIT":
            return True, "Early exit triggered correctly"
        return False, f"Expected EARLY_EXIT but got pipeline_status={result.pipeline_status}"

    if expected.get("decision") and result.decision and result.decision.value != expected["decision"]:
        return False, f"Expected decision={expected['decision']} but got {result.decision.value}"

    if expected.get("approved_amount") is not None:
        if result.approved_amount is None:
            return False, f"Expected approved_amount={expected['approved_amount']} but got None"
        if abs(result.approved_amount - expected["approved_amount"]) >= 1:
            return False, (
                f"Expected approved_amount={expected['approved_amount']} "
                f"but got {result.approved_amount}"
            )

    if expected.get("rejection_reasons"):
        for reason in expected["rejection_reasons"]:
            if reason not in (result.rejection_reasons or []):
                return False, f"Expected rejection reason '{reason}' not in {result.rejection_reasons}"

    return True, "PASS"


def main():
    pipeline = ClaimsPipeline()
    test_cases = load_test_cases()
    results = []
    passed = 0
    failed = 0

    for tc in test_cases:
        result = run_case(tc, pipeline)
        ok, reason = check_pass(result, tc["expected"])
        if ok:
            passed += 1
        else:
            failed += 1

        trace_dicts = [
            {
                "agent": step.agent,
                "status": step.status,
                "input_summary": step.input_summary,
                "output_summary": step.output_summary,
                "checks": step.checks,
                "error": step.error,
                "timestamp": step.timestamp,
            }
            for step in result.trace
        ]

        results.append({
            "case_id": tc["case_id"],
            "case_name": tc["case_name"],
            "description": tc["description"],
            "expected": tc["expected"],
            "actual": {
                "decision": result.decision.value if result.decision else None,
                "pipeline_status": result.pipeline_status,
                "approved_amount": result.approved_amount,
                "claimed_amount": result.claimed_amount,
                "confidence_score": result.confidence_score,
                "rejection_reasons": result.rejection_reasons,
                "partial_items": result.partial_items,
                "message": result.message,
                "trace": trace_dicts,
            },
            "passed": ok,
            "verdict": reason,
        })

        status_icon = "PASS" if ok else "FAIL"
        print(f"[{status_icon}] {tc['case_id']} — {tc['case_name']}")
        print(f"       Decision: {result.decision.value if result.decision else 'None'} | "
              f"Pipeline: {result.pipeline_status} | "
              f"Amount: {result.approved_amount} | "
              f"Confidence: {result.confidence_score}")
        if not ok:
            print(f"       REASON: {reason}")
        print()

    print(f"{'='*60}")
    print(f"TOTAL: {passed}/12 passed, {failed} failed")
    print(f"{'='*60}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": {"passed": passed, "failed": failed, "total": 12}, "cases": results}, f, indent=2, ensure_ascii=False)
    print(f"\nFull report written to: {out_path}")


if __name__ == "__main__":
    main()

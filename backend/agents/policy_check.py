from backend.agents.base import BaseAgent
from backend.policy.engine import PolicyEngine
from datetime import datetime


class PolicyCheckAgent(BaseAgent):
    def __init__(self, policy: PolicyEngine):
        super().__init__("PolicyCheckAgent")
        self.policy = policy

    def _parse_date(self, date_str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return None

    def run(self, context: dict) -> dict:
        if context.get("early_exit"):
            return context

        claim = context["claim"]
        extracted = context.get("extracted_data", {})
        checks = []
        rejection_reasons = []
        approved_amount = claim.claimed_amount
        partial_items = []

        # 1. Member validation
        member = self.policy.get_member(claim.member_id)
        if not member:
            checks.append(
                {
                    "check": "member_validation",
                    "status": "FAILED",
                    "detail": f"Member {claim.member_id} not found in policy",
                }
            )
            rejection_reasons.append("MEMBER_NOT_FOUND")
        else:
            checks.append(
                {
                    "check": "member_validation",
                    "status": "PASSED",
                    "detail": f"Member {member['name']} found, joined {member['join_date']}",
                }
            )

        # 2. Exclusions check — runs BEFORE waiting period / per-claim checks
        # because an excluded diagnosis is a hard stop that takes priority.
        diagnoses = extracted.get("diagnoses", [])
        line_items = extracted.get("line_items", [])
        exclusion_result = self.policy.check_exclusions(diagnoses, line_items)

        diagnosis_excluded = bool(exclusion_result.get("diagnosis_exclusion"))

        if diagnosis_excluded:
            # The diagnosis itself is on the exclusion list — entire claim excluded.
            # Mark every line item as excluded so the trace is fully visible.
            for item in line_items:
                partial_items.append(
                    {**item, "status": "EXCLUDED", "reason": exclusion_result["reason"]}
                )
            checks.append(
                {
                    "check": "exclusions",
                    "status": "FAILED",
                    "detail": (
                        f"Diagnosis matches excluded condition: "
                        f"{exclusion_result['diagnosis_exclusion']}. "
                        f"All line items excluded."
                    ),
                    "excluded_amount": claim.claimed_amount,
                }
            )
            approved_amount = 0
            rejection_reasons.append("EXCLUDED_CONDITION")

            # Hard stop — skip remaining checks, they are moot.
            context["policy_result"] = {
                "checks": checks,
                "rejection_reasons": rejection_reasons,
                "approved_amount": 0,
                "partial_items": partial_items,
                "financial_breakdown": {},
            }
            context["trace"].append(
                self.make_trace_step(
                    "COMPLETED_WITH_ISSUES",
                    input_summary=(
                        f"Member: {claim.member_id}, "
                        f"Category: {claim.claim_category.value}, "
                        f"Amount: ₹{claim.claimed_amount}"
                    ),
                    output_summary="EXCLUDED_CONDITION — diagnosis on exclusion list. Hard stop.",
                    checks=checks,
                )
            )
            return context

        elif exclusion_result["excluded_items"]:
            excluded_amount = sum(
                item.get("amount", 0) for item in exclusion_result["excluded_items"]
            )
            excluded_descs = {
                item.get("description", "").lower()
                for item in exclusion_result["excluded_items"]
            }
            approved_items = [
                item
                for item in line_items
                if item.get("description", "").lower() not in excluded_descs
            ]
            approved_amount_from_items = sum(
                item.get("amount", 0) for item in approved_items
            )

            checks.append(
                {
                    "check": "exclusions",
                    "status": "PARTIAL" if approved_items else "FAILED",
                    "detail": (
                        f"Excluded items: "
                        f"{[i['description'] for i in exclusion_result['excluded_items']]}"
                    ),
                    "excluded_amount": excluded_amount,
                }
            )

            for item in exclusion_result["excluded_items"]:
                partial_items.append(
                    {**item, "status": "EXCLUDED", "reason": exclusion_result["reason"]}
                )
            for item in approved_items:
                partial_items.append({**item, "status": "APPROVED"})

            if approved_items:
                approved_amount = approved_amount_from_items
                rejection_reasons.append("PARTIAL_EXCLUSION")
            else:
                approved_amount = 0
                rejection_reasons.append("EXCLUDED_CONDITION")
        else:
            checks.append(
                {"check": "exclusions", "status": "PASSED", "detail": "No exclusions found"}
            )

        # 3. Waiting period check
        if member:
            diagnosis_text = " ".join(diagnoses).lower()

            waiting_result = self.policy.check_waiting_period(
                member, diagnosis_text, claim.treatment_date
            )
            if waiting_result["violated"]:
                checks.append(
                    {
                        "check": "waiting_period",
                        "status": "FAILED",
                        "detail": waiting_result["message"],
                    }
                )
                rejection_reasons.append("WAITING_PERIOD")
            else:
                checks.append(
                    {
                        "check": "waiting_period",
                        "status": "PASSED",
                        "detail": "No waiting period violations",
                    }
                )

        # 4. Pre-authorization check
        tests = []
        for doc in extracted.get("documents", []):
            doc_data = doc.get("data", {})
            if doc_data.get("tests_ordered"):
                tests.extend(doc_data["tests_ordered"])
            if doc_data.get("test_name"):
                tests.append(doc_data["test_name"])

        pre_auth_result = self.policy.check_pre_auth(
            claim.claim_category.value, claim.claimed_amount, tests
        )
        if pre_auth_result["required"]:
            checks.append(
                {
                    "check": "pre_authorization",
                    "status": "FAILED",
                    "detail": (
                        pre_auth_result["reason"]
                        + " To resubmit: obtain pre-authorization from your insurer "
                        "before the procedure, then resubmit the claim with the "
                        "pre-auth reference number."
                    ),
                }
            )
            rejection_reasons.append("PRE_AUTH_MISSING")
        else:
            checks.append(
                {
                    "check": "pre_authorization",
                    "status": "PASSED",
                    "detail": "Pre-authorization not required or already obtained",
                }
            )

        # 5. Per-claim limit check
        # Use the category sub_limit if one is defined — it overrides the global per_claim_limit.
        category_config_for_limit = self.policy.get_opd_category(claim.claim_category.value)
        effective_limit_amount = approved_amount  # check the post-exclusion amount
        limit_result = self.policy.check_per_claim_limit(
            effective_limit_amount, category_config_for_limit
        )
        if limit_result["exceeded"]:
            checks.append(
                {
                    "check": "per_claim_limit",
                    "status": "FAILED",
                    "detail": (
                        f"Claimed amount ₹{claim.claimed_amount:,.0f} exceeds per-claim limit "
                        f"of ₹{limit_result['limit']:,.0f}"
                    ),
                }
            )
            rejection_reasons.append("PER_CLAIM_EXCEEDED")
        else:
            checks.append(
                {
                    "check": "per_claim_limit",
                    "status": "PASSED",
                    "detail": (
                        f"Claimed ₹{claim.claimed_amount:,.0f} is within per-claim limit "
                        f"of ₹{limit_result['limit']:,.0f}"
                    ),
                }
            )

        # 6. Network discount + co-pay (only when claim is not outright rejected)
        financial_breakdown = {}
        hard_rejections = [
            r for r in rejection_reasons
            if r not in ("PARTIAL_EXCLUSION",)
        ]
        if not hard_rejections:
            category_config = self.policy.get_opd_category(claim.claim_category.value)
            if category_config:
                hospital_name = (
                    extracted.get("hospital_name") or claim.hospital_name or ""
                )
                base = approved_amount

                if self.policy.is_network_hospital(hospital_name):
                    discount_pct = category_config.get("network_discount_percent", 0)
                    discounted = base * (1 - discount_pct / 100)
                    financial_breakdown["network_discount"] = {
                        "applied": True,
                        "hospital": hospital_name,
                        "discount_percent": discount_pct,
                        "before": base,
                        "after": round(discounted, 2),
                    }
                    base = discounted
                    checks.append(
                        {
                            "check": "network_discount",
                            "status": "APPLIED",
                            "detail": (
                                f"Network discount {discount_pct}% applied: "
                                f"₹{approved_amount:,.0f} → ₹{base:,.2f}"
                            ),
                        }
                    )

                copay_pct = category_config.get("copay_percent", 0)
                if copay_pct > 0:
                    copay = base * (copay_pct / 100)
                    approved_amount = base - copay
                    financial_breakdown["copay"] = {
                        "percent": copay_pct,
                        "amount": round(copay, 2),
                        "before": round(base, 2),
                        "after": round(approved_amount, 2),
                    }
                    checks.append(
                        {
                            "check": "copay",
                            "status": "APPLIED",
                            "detail": (
                                f"Co-pay {copay_pct}% deducted: ₹{copay:,.2f}. "
                                f"Final approved: ₹{approved_amount:,.2f}"
                            ),
                        }
                    )
                else:
                    checks.append(
                        {
                            "check": "copay",
                            "status": "NOT_APPLICABLE",
                            "detail": "No co-pay for this category",
                        }
                    )

        context["policy_result"] = {
            "checks": checks,
            "rejection_reasons": rejection_reasons,
            "approved_amount": round(approved_amount, 2),
            "partial_items": partial_items,
            "financial_breakdown": financial_breakdown,
        }

        status = "SUCCESS" if not rejection_reasons else "COMPLETED_WITH_ISSUES"
        context["trace"].append(
            self.make_trace_step(
                status,
                input_summary=(
                    f"Member: {claim.member_id}, "
                    f"Category: {claim.claim_category.value}, "
                    f"Amount: ₹{claim.claimed_amount}"
                ),
                output_summary=(
                    f"Rejection reasons: {rejection_reasons or 'None'}. "
                    f"Approved: ₹{approved_amount}"
                ),
                checks=checks,
            )
        )
        return context

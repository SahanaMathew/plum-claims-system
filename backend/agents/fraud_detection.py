from backend.agents.base import BaseAgent
from backend.policy.engine import PolicyEngine


class FraudDetectionAgent(BaseAgent):
    def __init__(self, policy: PolicyEngine):
        super().__init__("FraudDetectionAgent")
        self.policy = policy

    def run(self, context: dict) -> dict:
        if context.get("early_exit"):
            return context

        claim = context["claim"]
        fraud_signals = []
        fraud_score = 0.0
        checks = []

        thresholds = self.policy.data.get("fraud_thresholds", {})
        same_day_limit = thresholds.get("same_day_claims_limit", 2)
        high_value_threshold = thresholds.get("high_value_claim_threshold", 25000)
        fraud_review_threshold = thresholds.get("fraud_score_manual_review_threshold", 0.80)

        # 1. Same-day claims check
        history = claim.claims_history or []
        treatment_date = claim.treatment_date
        same_day_claims = [c for c in history if c.get("date") == treatment_date]

        if len(same_day_claims) >= same_day_limit:
            signal = {
                "signal": "EXCESSIVE_SAME_DAY_CLAIMS",
                "detail": (
                    f"Member has {len(same_day_claims)} existing claims on {treatment_date} "
                    f"(limit: {same_day_limit}). "
                    f"This is claim #{len(same_day_claims) + 1} on the same day."
                ),
                "previous_claims": same_day_claims,
            }
            fraud_signals.append(signal)
            fraud_score += 0.85
            checks.append(
                {
                    "check": "same_day_claims",
                    "status": "FLAGGED",
                    "detail": signal["detail"],
                    "count": len(same_day_claims),
                }
            )
        else:
            checks.append(
                {
                    "check": "same_day_claims",
                    "status": "PASSED",
                    "detail": (
                        f"{len(same_day_claims)} same-day claim(s) found (limit: {same_day_limit})"
                    ),
                }
            )

        # 2. High value check
        if claim.claimed_amount >= high_value_threshold:
            signal = {
                "signal": "HIGH_VALUE_CLAIM",
                "detail": (
                    f"Claimed amount ₹{claim.claimed_amount:,.0f} exceeds high-value threshold "
                    f"of ₹{high_value_threshold:,.0f}"
                ),
            }
            fraud_signals.append(signal)
            fraud_score += 0.3
            checks.append(
                {"check": "high_value", "status": "FLAGGED", "detail": signal["detail"]}
            )
        else:
            checks.append(
                {
                    "check": "high_value",
                    "status": "PASSED",
                    "detail": (
                        f"₹{claim.claimed_amount:,.0f} is below high-value threshold "
                        f"of ₹{high_value_threshold:,.0f}"
                    ),
                }
            )

        fraud_score = min(fraud_score, 1.0)
        requires_manual_review = fraud_score >= fraud_review_threshold

        context["fraud_result"] = {
            "fraud_score": round(fraud_score, 2),
            "signals": fraud_signals,
            "requires_manual_review": requires_manual_review,
            "checks": checks,
        }

        status = "FLAGGED" if fraud_signals else "CLEAR"
        context["trace"].append(
            self.make_trace_step(
                status,
                input_summary=(
                    f"Checking {len(history)} historical claims, "
                    f"amount ₹{claim.claimed_amount}"
                ),
                output_summary=(
                    f"Fraud score: {fraud_score:.2f}. "
                    f"Signals: {[s['signal'] for s in fraud_signals] or 'None'}"
                ),
                checks=checks,
            )
        )
        return context

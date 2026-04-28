from backend.agents.base import BaseAgent


class DecisionAgent(BaseAgent):
    def __init__(self):
        super().__init__("DecisionAgent")

    def run(self, context: dict) -> dict:
        if context.get("early_exit"):
            return context

        claim = context["claim"]
        policy_result = context.get("policy_result", {})
        fraud_result = context.get("fraud_result", {})
        extracted = context.get("extracted_data", {})

        rejection_reasons = policy_result.get("rejection_reasons", [])
        approved_amount = policy_result.get("approved_amount", claim.claimed_amount)
        partial_items = policy_result.get("partial_items", [])
        fraud_signals = fraud_result.get("signals", [])
        fraud_score = fraud_result.get("fraud_score", 0.0)

        # Confidence calculation
        confidence = 1.0
        if extracted.get("extraction_errors"):
            confidence -= 0.1 * len(extracted["extraction_errors"])
        if context.get("component_failed"):
            confidence -= 0.25
        if fraud_signals and not fraud_result.get("requires_manual_review"):
            confidence -= 0.1 * len(fraud_signals)
        confidence = max(0.1, round(confidence, 2))

        checks = []

        # --- Decision logic ---

        if fraud_result.get("requires_manual_review"):
            decision = "MANUAL_REVIEW"
            message = (
                f"This claim has been flagged for manual review due to unusual patterns: "
                f"{'; '.join(s['detail'] for s in fraud_signals)}. "
                f"A claims officer will review within 2-3 business days."
            )
            approved_amount = None
            checks.append(
                {
                    "check": "final_decision",
                    "status": "MANUAL_REVIEW",
                    "detail": f"Fraud score {fraud_score:.2f} exceeded manual review threshold",
                }
            )

        elif rejection_reasons and set(rejection_reasons) - {"PARTIAL_EXCLUSION"}:
            # There are hard rejection reasons beyond a partial exclusion
            actual_reasons = [r for r in rejection_reasons if r != "PARTIAL_EXCLUSION"]
            decision = "REJECTED"

            reason_messages = []
            for check in policy_result.get("checks", []):
                if check.get("status") == "FAILED":
                    reason_messages.append(check["detail"])

            message = (
                "Claim rejected. " + " | ".join(reason_messages)
                if reason_messages
                else f"Claim rejected: {', '.join(actual_reasons)}"
            )
            approved_amount = 0
            checks.append(
                {
                    "check": "final_decision",
                    "status": "REJECTED",
                    "reasons": actual_reasons,
                }
            )

        elif "PARTIAL_EXCLUSION" in rejection_reasons or partial_items:
            decision = "PARTIAL"
            excluded = [i for i in partial_items if i.get("status") == "EXCLUDED"]
            approved = [i for i in partial_items if i.get("status") == "APPROVED"]

            lines = []
            for item in approved:
                lines.append(
                    f"  APPROVED: {item.get('description', 'Item')} — "
                    f"Rs {item.get('amount', 0):,.0f}"
                )
            for item in excluded:
                lines.append(
                    f"  EXCLUDED: {item.get('description', 'Item')} — "
                    f"Rs {item.get('amount', 0):,.0f} "
                    f"({item.get('reason', 'policy exclusion')})"
                )

            message = (
                f"Partial approval: Rs {approved_amount:,.0f} approved out of "
                f"Rs {claim.claimed_amount:,.0f} claimed.\n" + "\n".join(lines)
            )
            checks.append(
                {
                    "check": "final_decision",
                    "status": "PARTIAL",
                    "approved_items": len(approved),
                    "excluded_items": len(excluded),
                }
            )

        else:
            decision = "APPROVED"
            breakdown = policy_result.get("financial_breakdown", {})
            breakdown_notes = []

            if breakdown.get("network_discount", {}).get("applied"):
                nd = breakdown["network_discount"]
                breakdown_notes.append(
                    f"Network discount {nd['discount_percent']}% applied "
                    f"(Rs {nd['before']:,.0f} -> Rs {nd['after']:,.2f})"
                )
            if breakdown.get("copay"):
                cp = breakdown["copay"]
                breakdown_notes.append(
                    f"Co-pay {cp['percent']}% deducted: Rs {cp['amount']:,.2f}"
                )

            message = f"Claim approved for Rs {approved_amount:,.2f}."
            if breakdown_notes:
                message += " " + ". ".join(breakdown_notes) + "."
            checks.append(
                {
                    "check": "final_decision",
                    "status": "APPROVED",
                    "amount": approved_amount,
                }
            )

        # Component failure note
        if context.get("component_failed"):
            message += (
                " Note: One or more pipeline components failed during processing. "
                "Manual review is recommended."
            )
            confidence = min(confidence, 0.65)

        context["final_decision"] = {
            "decision": decision,
            "approved_amount": approved_amount,
            "confidence_score": confidence,
            "rejection_reasons": [r for r in rejection_reasons if r != "PARTIAL_EXCLUSION"],
            "partial_items": partial_items,
            "message": message,
        }

        context["trace"].append(
            self.make_trace_step(
                "SUCCESS",
                input_summary=(
                    f"Policy rejections: {rejection_reasons}, "
                    f"Fraud score: {fraud_score}"
                ),
                output_summary=(
                    f"Decision: {decision}, "
                    f"Amount: Rs {approved_amount}, "
                    f"Confidence: {confidence}"
                ),
                checks=checks,
            )
        )
        return context

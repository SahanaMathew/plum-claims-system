from backend.agents.document_verification import DocumentVerificationAgent
from backend.agents.extraction import ExtractionAgent
from backend.agents.policy_check import PolicyCheckAgent
from backend.agents.fraud_detection import FraudDetectionAgent
from backend.agents.decision import DecisionAgent
from backend.policy.engine import PolicyEngine
from backend.models.schemas import ClaimSubmission, ClaimDecision, TraceStep
from backend.config import POLICY_FILE
from datetime import datetime
import traceback


class ClaimsPipeline:
    def __init__(self):
        self.policy = PolicyEngine(POLICY_FILE)
        self.agents = [
            DocumentVerificationAgent(self.policy),
            ExtractionAgent(),
            PolicyCheckAgent(self.policy),
            FraudDetectionAgent(self.policy),
            DecisionAgent(),
        ]

    def process(self, claim: ClaimSubmission) -> ClaimDecision:
        context = {
            "claim": claim,
            "trace": [],
            "early_exit": False,
            "component_failed": False,
        }

        # Index of the agent to fail when simulating component failure (TC011)
        # Fail PolicyCheckAgent (index 2) to produce a degraded-but-runnable pipeline
        failed_agent_index = None
        if claim.simulate_component_failure:
            failed_agent_index = 2

        for i, agent in enumerate(self.agents):
            try:
                if i == failed_agent_index:
                    raise RuntimeError("Simulated component failure for testing")

                context = agent.run(context)

                if context.get("early_exit"):
                    break

            except Exception as e:
                context["component_failed"] = True
                context["trace"].append(
                    TraceStep(
                        agent=agent.name,
                        status="FAILED",
                        error=str(e),
                        output_summary=(
                            f"Component failed: {str(e)}. "
                            "Pipeline continuing in degraded mode."
                        ),
                        timestamp=datetime.utcnow().isoformat(),
                    )
                )
                # Continue — do not crash the pipeline
                continue

        # Build the final response
        if context.get("early_exit"):
            return ClaimDecision(
                claim_id=claim.claim_id,
                member_id=claim.member_id,
                decision=None,
                claimed_amount=claim.claimed_amount,
                approved_amount=None,
                confidence_score=None,
                message=context.get(
                    "early_exit_message",
                    "Claim cannot be processed due to document issues.",
                ),
                trace=context["trace"],
                pipeline_status="EARLY_EXIT",
            )

        final = context.get("final_decision", {})
        pipeline_status = "DEGRADED" if context.get("component_failed") else "COMPLETE"

        return ClaimDecision(
            claim_id=claim.claim_id,
            member_id=claim.member_id,
            decision=final.get("decision"),
            approved_amount=final.get("approved_amount"),
            claimed_amount=claim.claimed_amount,
            confidence_score=final.get("confidence_score"),
            rejection_reasons=final.get("rejection_reasons", []),
            partial_items=final.get("partial_items", []),
            message=final.get("message", "Processing complete."),
            trace=context["trace"],
            pipeline_status=pipeline_status,
        )

from backend.agents.base import BaseAgent
from backend.policy.engine import PolicyEngine


class DocumentVerificationAgent(BaseAgent):
    def __init__(self, policy: PolicyEngine):
        super().__init__("DocumentVerificationAgent")
        self.policy = policy

    def run(self, context: dict) -> dict:
        claim = context["claim"]
        docs = claim.documents
        category = claim.claim_category.value
        checks = []

        # 1. Document type check
        requirements = self.policy.get_document_requirements(category)
        uploaded_types = [d.actual_type for d in docs if d.actual_type]

        missing_required = []
        for req_type in requirements["required"]:
            if req_type not in uploaded_types:
                missing_required.append(req_type)

        if missing_required:
            # Identify what was uploaded that is not expected
            all_expected = requirements["required"] + requirements.get("optional", [])
            wrong_types = [t for t in uploaded_types if t not in all_expected]

            if wrong_types:
                message = (
                    f"Document type mismatch: You uploaded {', '.join(wrong_types)} but a "
                    f"{', '.join(missing_required)} is required for a {category} claim. "
                    f"Please replace the incorrect document(s) with the required type(s)."
                )
            else:
                message = (
                    f"Missing required documents for {category} claim: "
                    f"{', '.join(missing_required)} not found in your submission. "
                    f"Please upload the required document(s) to proceed."
                )

            checks.append({"check": "document_types", "status": "FAILED", "detail": message})
            context["early_exit"] = True
            context["early_exit_message"] = message
            context["trace"].append(
                self.make_trace_step(
                    "EARLY_EXIT",
                    input_summary=f"Uploaded: {uploaded_types}, Required: {requirements['required']}",
                    output_summary=message,
                    checks=checks,
                )
            )
            return context

        # 2. Readability check
        for doc in docs:
            if doc.quality == "UNREADABLE":
                message = (
                    f"The document '{doc.file_name or doc.file_id}' (type: {doc.actual_type}) "
                    f"could not be read — the image is too blurry or unclear. "
                    f"Please re-upload a clear photo or scan of this document to proceed."
                )
                checks.append(
                    {
                        "check": "readability",
                        "status": "FAILED",
                        "detail": message,
                        "file_id": doc.file_id,
                    }
                )
                context["early_exit"] = True
                context["early_exit_message"] = message
                context["trace"].append(
                    self.make_trace_step(
                        "EARLY_EXIT",
                        input_summary=f"Checked {len(docs)} documents",
                        output_summary=message,
                        checks=checks,
                    )
                )
                return context

        # 3. Cross-patient check
        named_docs = [
            (d.file_name or d.file_id, d.patient_name_on_doc)
            for d in docs
            if d.patient_name_on_doc
        ]
        if named_docs:
            unique_names = list(set(name for _, name in named_docs))
            if len(unique_names) > 1:
                detail = "; ".join([f"{fname}: {pname}" for fname, pname in named_docs])
                message = (
                    f"Patient name mismatch across documents: {detail}. "
                    f"All documents in a single claim must belong to the same patient. "
                    f"Please ensure all uploaded documents are for the same person."
                )
                checks.append({"check": "cross_patient", "status": "FAILED", "detail": message})
                context["early_exit"] = True
                context["early_exit_message"] = message
                context["trace"].append(
                    self.make_trace_step(
                        "EARLY_EXIT",
                        input_summary=f"Patient names found: {unique_names}",
                        output_summary=message,
                        checks=checks,
                    )
                )
                return context

        checks.append(
            {
                "check": "all_document_checks",
                "status": "PASSED",
                "detail": f"All required documents present and valid for {category} claim",
            }
        )
        context["doc_verification"] = {"status": "PASSED"}
        context["trace"].append(
            self.make_trace_step(
                "SUCCESS",
                input_summary=f"Uploaded: {uploaded_types}, Required: {requirements['required']}",
                output_summary="All document checks passed",
                checks=checks,
            )
        )
        return context

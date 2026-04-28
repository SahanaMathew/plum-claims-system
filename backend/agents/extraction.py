from backend.agents.base import BaseAgent


class ExtractionAgent(BaseAgent):
    def __init__(self):
        super().__init__("ExtractionAgent")

    def _extract_from_content(self, doc) -> dict:
        """Use provided content directly (test case mode)."""
        if doc.content:
            return {**doc.content, "extraction_method": "provided_content", "quality": "GOOD"}
        return {"error": "No content available", "extraction_method": "none"}

    def _extract_with_llm(self, doc) -> dict:
        """Use LLM to extract structured information from a document description."""
        system = (
            "You are a medical document extraction AI specializing in Indian healthcare documents. "
            "Extract all available information from the document and return as JSON with these fields: "
            "patient_name, doctor_name, doctor_registration, date, diagnosis, treatment, "
            "medicines (list), test_names (list), line_items (list of {description, amount}), "
            "total_amount, hospital_name, notes. Use null for missing fields."
        )
        user = (
            f"Document type: {doc.actual_type}\n"
            f"File: {doc.file_name}\n"
            "Extract all available information from this document."
        )
        result = self._call_llm(system, user)
        result["extraction_method"] = "llm"
        return result

    def run(self, context: dict) -> dict:
        if context.get("early_exit"):
            return context

        claim = context["claim"]
        extracted_docs = []
        errors = []

        for doc in claim.documents:
            try:
                if doc.content:
                    data = self._extract_from_content(doc)
                else:
                    data = self._extract_with_llm(doc)
                extracted_docs.append(
                    {"file_id": doc.file_id, "type": doc.actual_type, "data": data}
                )
            except Exception as e:
                errors.append({"file_id": doc.file_id, "error": str(e)})
                extracted_docs.append(
                    {
                        "file_id": doc.file_id,
                        "type": doc.actual_type,
                        "data": {"error": str(e)},
                    }
                )

        # Synthesize across all documents
        all_line_items = []
        patient_names = set()
        diagnoses = []
        hospital_names = set()

        for ed in extracted_docs:
            d = ed["data"]
            if d.get("patient_name"):
                patient_names.add(d["patient_name"])
            if d.get("diagnosis"):
                diagnoses.append(d["diagnosis"])
            if d.get("hospital_name"):
                hospital_names.add(d["hospital_name"])
            if d.get("line_items"):
                all_line_items.extend(d["line_items"])

        context["extracted_data"] = {
            "documents": extracted_docs,
            "primary_patient_name": list(patient_names)[0] if patient_names else None,
            "all_patient_names": list(patient_names),
            "diagnoses": diagnoses,
            "line_items": all_line_items,
            "hospital_name": (
                list(hospital_names)[0] if hospital_names else claim.hospital_name
            ),
            "extraction_errors": errors,
        }

        status = "SUCCESS" if not errors else "PARTIAL"
        context["trace"].append(
            self.make_trace_step(
                status,
                input_summary=f"Extracting from {len(claim.documents)} documents",
                output_summary=(
                    f"Extracted data from {len(extracted_docs)} docs. "
                    f"Diagnoses: {diagnoses}. Line items: {len(all_line_items)}"
                ),
                checks=[{"check": "extraction", "status": status, "errors": errors}],
            )
        )
        return context

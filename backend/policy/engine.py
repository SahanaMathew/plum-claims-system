import json
from datetime import datetime, date, timedelta
from typing import Optional, List


class PolicyEngine:
    def __init__(self, policy_file: str):
        with open(policy_file) as f:
            self.data = json.load(f)
        self._members = {m["member_id"]: m for m in self.data.get("members", [])}

    def get_member(self, member_id: str) -> Optional[dict]:
        return self._members.get(member_id)

    def get_document_requirements(self, claim_category: str) -> dict:
        return self.data.get("document_requirements", {}).get(
            claim_category, {"required": [], "optional": []}
        )

    def get_opd_category(self, claim_category: str) -> Optional[dict]:
        category_map = {
            "CONSULTATION": "consultation",
            "DIAGNOSTIC": "diagnostic",
            "PHARMACY": "pharmacy",
            "DENTAL": "dental",
            "VISION": "vision",
            "ALTERNATIVE_MEDICINE": "alternative_medicine",
        }
        key = category_map.get(claim_category)
        return self.data.get("opd_categories", {}).get(key) if key else None

    def is_network_hospital(self, hospital_name: str) -> bool:
        if not hospital_name:
            return False
        hospital_lower = hospital_name.lower()
        return any(
            nh.lower() in hospital_lower or hospital_lower in nh.lower()
            for nh in self.data.get("network_hospitals", [])
        )

    def check_waiting_period(self, member: dict, diagnosis_text: str, treatment_date: str) -> dict:
        join_date = datetime.strptime(member["join_date"], "%Y-%m-%d").date()
        treatment = datetime.strptime(treatment_date, "%Y-%m-%d").date()
        waiting_periods = self.data.get("waiting_periods", {})

        # Initial waiting period
        initial_days = waiting_periods.get("initial_waiting_period_days", 30)
        eligible_after_initial = join_date + timedelta(days=initial_days)
        if treatment < eligible_after_initial:
            return {
                "violated": True,
                "condition": "initial_waiting_period",
                "eligible_from": eligible_after_initial.isoformat(),
                "message": (
                    f"Treatment date {treatment_date} is within the {initial_days}-day initial "
                    f"waiting period (joined {member['join_date']}). "
                    f"Eligible from {eligible_after_initial.isoformat()}."
                ),
            }

        # Specific condition waiting periods
        condition_map = {
            "diabetes": ["diabetes", "diabetic", "metformin", "glimepiride", "insulin"],
            "hypertension": ["hypertension", "blood pressure", "bp", "amlodipine"],
            "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid"],
            "joint_replacement": ["joint replacement", "knee replacement", "hip replacement"],
            "maternity": ["maternity", "pregnancy", "prenatal", "antenatal", "obstetric"],
            "mental_health": ["mental health", "depression", "anxiety", "psychiatric"],
            "obesity_treatment": ["obesity", "bariatric", "weight loss", "bmi"],
            "hernia": ["hernia"],
            "cataract": ["cataract"],
        }

        for condition, keywords in condition_map.items():
            if any(kw in diagnosis_text for kw in keywords):
                wait_days = waiting_periods.get("specific_conditions", {}).get(condition, 0)
                if wait_days > 0:
                    eligible_from = join_date + timedelta(days=wait_days)
                    if treatment < eligible_from:
                        return {
                            "violated": True,
                            "condition": condition,
                            "wait_days": wait_days,
                            "eligible_from": eligible_from.isoformat(),
                            "message": (
                                f"Treatment for {condition.replace('_', ' ')} is within the "
                                f"{wait_days}-day waiting period "
                                f"(joined {member['join_date']}). "
                                f"Eligible from {eligible_from.isoformat()}."
                            ),
                        }

        return {"violated": False}

    # Key terms that uniquely identify each exclusion category.
    # When any of these appears in text, the exclusion is triggered.
    _EXCLUSION_KEYWORDS: dict = {
        "self-inflicted injuries": ["self-inflicted"],
        "war or nuclear hazard": ["nuclear"],
        "substance abuse treatment": ["substance abuse"],
        "experimental treatments": ["experimental"],
        "infertility and assisted reproduction": ["infertility", "assisted reproduction"],
        "obesity and weight loss programs": ["obesity", "bariatric", "weight loss", "bmi"],
        "bariatric surgery": ["bariatric"],
        "cosmetic or aesthetic procedures": ["cosmetic", "aesthetic", "whitening", "bleaching", "veneers"],
        "vaccination (non-medically necessary)": ["vaccination"],
        "health supplements and tonics": ["supplements", "tonics"],
        "teeth whitening": ["whitening", "teeth whitening"],
        "orthodontic treatment": ["orthodontic", "braces"],
        "cosmetic dental procedures": ["cosmetic dental"],
        "lasik": ["lasik"],
        "refractive surgery": ["refractive surgery"],
    }

    def _matches_exclusion(self, text: str, excl_phrase: str) -> bool:
        """
        Return True if `text` matches `excl_phrase`.

        Uses a curated keyword map first; falls back to phrase/word matching.
        """
        import re
        text_lower = text.lower()
        excl_lower = excl_phrase.lower()

        # 1. Direct phrase match (handles exact strings like "teeth whitening")
        if excl_lower in text_lower:
            return True

        # 2. Curated keyword map (most reliable)
        keywords = self._EXCLUSION_KEYWORDS.get(excl_lower)
        if keywords:
            return any(kw in text_lower for kw in keywords)

        # 3. For multi-word exclusions not in the map: require ≥2 of the
        #    most distinctive words (len > 5) to appear together
        words = [w for w in excl_lower.split() if len(w) > 5]
        if len(words) >= 2:
            return sum(1 for w in words if w in text_lower) >= 2
        if len(words) == 1:
            return bool(re.search(r'\b' + re.escape(words[0]) + r'\b', text_lower))

        # 4. Single-word exclusion: whole-word match
        return bool(re.search(r'\b' + re.escape(excl_lower) + r'\b', text_lower))

    def check_exclusions(self, diagnoses: list, line_items: list) -> dict:
        exclusions = self.data.get("exclusions", {})
        excluded_conditions = [c.lower() for c in exclusions.get("conditions", [])]
        excluded_dental = [c.lower() for c in exclusions.get("dental_exclusions", [])]
        excluded_vision = [c.lower() for c in exclusions.get("vision_exclusions", [])]
        all_excluded = excluded_conditions + excluded_dental + excluded_vision

        excluded_items = []
        reason = None

        # Check each line item description against exclusion terms
        for item in line_items:
            desc = item.get("description", "").lower()
            matched_excl = None
            for excl in all_excluded:
                if self._matches_exclusion(desc, excl):
                    matched_excl = excl
                    break
            if matched_excl:
                excluded_items.append({**item, "exclusion_matched": matched_excl})
                if not reason:
                    reason = f"Policy exclusion: {matched_excl}"

        # Check diagnosis text against exclusion terms
        diagnosis_text = " ".join(diagnoses).lower()
        diagnosis_exclusion = None
        for excl in all_excluded:
            if self._matches_exclusion(diagnosis_text, excl):
                diagnosis_exclusion = excl
                if not reason:
                    reason = f"Policy exclusion: {excl}"
                break

        return {
            "excluded_items": excluded_items,
            "diagnosis_exclusion": diagnosis_exclusion,
            "reason": reason,
        }

    def check_pre_auth(self, claim_category: str, amount: float, tests: List[str]) -> dict:
        if claim_category != "DIAGNOSTIC":
            return {"required": False}

        diagnostic_cfg = self.data.get("opd_categories", {}).get("diagnostic", {})
        high_value_tests = diagnostic_cfg.get("high_value_tests_requiring_pre_auth", [])
        pre_auth_threshold = diagnostic_cfg.get("pre_auth_threshold", 10000)

        for test in tests:
            for hvt in high_value_tests:
                if hvt.lower() in test.lower():
                    if amount > pre_auth_threshold:
                        return {
                            "required": True,
                            "reason": (
                                f"Pre-authorization is required for {test} when the claimed amount "
                                f"exceeds ₹{pre_auth_threshold:,.0f}. "
                                f"The claimed amount of ₹{amount:,.0f} requires prior approval."
                            ),
                        }

        return {"required": False}

    def check_per_claim_limit(self, amount: float, category_config: dict = None) -> dict:
        global_limit = self.data.get("coverage", {}).get("per_claim_limit", 5000)
        # If the category has its own sub_limit, use whichever is higher — the sub_limit
        # represents the category-specific cap and overrides the global per-claim floor.
        sub_limit = (category_config or {}).get("sub_limit")
        limit = max(global_limit, sub_limit) if sub_limit else global_limit
        return {"exceeded": amount > limit, "limit": limit}

    def apply_network_discount(self, amount: float, hospital_name: str, category_config: dict) -> float:
        if self.is_network_hospital(hospital_name):
            discount = category_config.get("network_discount_percent", 0)
            return amount * (1 - discount / 100)
        return amount

    def apply_copay(self, amount: float, category_config: dict) -> dict:
        copay_pct = category_config.get("copay_percent", 0)
        copay = amount * (copay_pct / 100)
        return {"approved": amount - copay, "copay": copay}

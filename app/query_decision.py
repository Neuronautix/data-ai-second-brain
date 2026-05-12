from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.schemas import DecisionOutput, Evidence, ProvisionalDecision, ProjectCard


KEYWORD_CONDITIONS: list[tuple[str, str]] = [
    ("condition.uses_patient_data", "patient"),
    ("condition.uses_identifiable_data", "identifiable"),
    ("condition.uses_pseudonymized_data", "pseudonym"),
    ("condition.has_external_partner", "partner"),
    ("condition.external_data_access_requested", "external access"),
    ("condition.uses_ai", "ai"),
    ("condition.clinical_deployment", "clinical deployment"),
    ("condition.research_only", "research"),
    ("condition.data_export_requested", "export"),
    ("condition.processing_outside_hospital_environment", "outside hospital"),
]


def _to_project_card(text: str) -> ProjectCard:
    lowered = text.lower()
    missing = []
    if "finality" not in lowered and "purpose" not in lowered:
        missing.append("Project finality is unclear")
    if "legal basis" not in lowered:
        missing.append("Legal basis is not specified")

    return ProjectCard(
        title="Project triage",
        summary=text.strip(),
        purpose="unknown" if "purpose" not in lowered else "provided",
        missing_information=missing,
    )


def _detect_conditions(text: str) -> list[str]:
    lowered = text.lower()
    conditions: list[str] = []
    for condition_id, keyword in KEYWORD_CONDITIONS:
        if keyword in lowered:
            conditions.append(condition_id)

    if "legal basis" not in lowered:
        conditions.append("condition.unknown_legal_basis")
    if "finality" not in lowered and "purpose" not in lowered:
        conditions.append("condition.unclear_finality")
    return sorted(set(conditions))


def decide(project_text: str, kb_path: Path = Path("data/kb/kb.json")) -> DecisionOutput:
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    rules = kb.get("rules", [])

    card = _to_project_card(project_text)
    conditions = _detect_conditions(project_text)

    activated_rules = []
    recommended_actions = []
    risks = []
    evidence: list[Evidence] = []

    for rule in rules:
        triggers = set(rule.get("trigger_conditions", []))
        if triggers and triggers.issubset(set(conditions)):
            activated_rules.append(rule["id"])
            recommended_actions.extend(rule.get("recommended_actions", []))
            risks.append(rule.get("label", rule["id"]))
            for ev in rule.get("evidence", []):
                evidence.append(Evidence.model_validate(ev))

    blocked = {
        "rule.unclear_finality_blocks_decision",
        "rule.unknown_legal_basis_blocks_decision",
    }
    if blocked.intersection(activated_rules):
        decision = ProvisionalDecision.insufficient_information
    elif "rule.data_export_requires_specific_validation" in activated_rules:
        decision = ProvisionalDecision.conditional_go
    elif activated_rules:
        decision = ProvisionalDecision.conditional_go
    else:
        decision = ProvisionalDecision.go

    rationale = "Requires DPO/legal validation for any provisional decision."

    return DecisionOutput(
        provisional_decision=decision,
        rationale=rationale,
        activated_conditions=conditions,
        activated_rules=sorted(set(activated_rules)),
        missing_information=card.missing_information,
        risks=sorted(set(risks)),
        recommended_actions=sorted(set(recommended_actions)),
        evidence=evidence,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Project triage decision helper")
    parser.add_argument("project", help="Free text project description")
    parser.add_argument("--kb", type=Path, default=Path("data/kb/kb.json"))
    args = parser.parse_args()

    output = decide(args.project, kb_path=args.kb)
    print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

from app.query_decision import decide


def test_patient_data_triggers_dpo_review(tmp_path):
    output = decide(
        "AI research on patient records with purpose and legal basis contract specified.",
    )
    assert "rule.dpo_review_required_for_health_data" in output.activated_rules


def test_external_partner_triggers_contractual_framing():
    output = decide(
        "Project uses patient data with private partner. purpose and legal basis documented.",
    )
    assert "rule.external_partner_requires_contractual_framing" in output.activated_rules


def test_unknown_legal_basis_blocks_decision():
    output = decide("Project uses patient data for research purpose with external partner.")
    assert output.provisional_decision.value in {"conditional_go", "insufficient_information"}
    assert "rule.unknown_legal_basis_blocks_decision" in output.activated_rules


def test_unclear_finality_blocks_decision():
    output = decide("Project uses patient data and AI model with legal basis documented.")
    assert output.provisional_decision.value == "insufficient_information"
    assert "rule.unclear_finality_blocks_decision" in output.activated_rules

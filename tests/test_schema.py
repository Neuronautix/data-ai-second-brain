import pytest
from pydantic import ValidationError

from app.schemas import Evidence, Rule, Severity


def test_rule_requires_evidence() -> None:
    """source_supported rules require at least one evidence item."""
    with pytest.raises(ValidationError):
        Rule(
            id="rule.invalid",
            label="Invalid",
            description="No evidence",
            domain="gdpr",
            severity=Severity.high,
            evidence_status="source_supported",  # type: ignore[arg-type]
            evidence=[],
        )


def test_rule_with_evidence_is_valid() -> None:
    rule = Rule(
        id="rule.valid",
        label="Valid",
        description="Has evidence",
        domain="gdpr",
        severity=Severity.medium,
        evidence=[
            Evidence(
                source_id="src.1",
                chunk_id="chunk.1",
                quote_or_summary="Supported",
            )
        ],
    )
    assert rule.id == "rule.valid"

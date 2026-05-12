import pytest
from pydantic import ValidationError

from app.schemas import KnowledgePayload


def test_knowledge_payload_rejects_rule_without_evidence() -> None:
    with pytest.raises(ValidationError):
        KnowledgePayload.model_validate(
            {
                "rules": [
                    {
                        "id": "rule.bad",
                        "label": "Bad",
                        "description": "No evidence",
                        "domain": "gdpr",
                        "severity": "high",
                        "evidence": [],
                    }
                ]
            }
        )

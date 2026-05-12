"""Tests for the LLM extraction pipeline and schema validation."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas import (
    Action,
    Concept,
    Condition,
    Evidence,
    EvidenceStatus,
    ExtractionResult,
    KnowledgePayload,
    Relation,
    Rule,
    Severity,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_evidence(**kwargs) -> dict:
    base = {
        "source_id": "src.test",
        "chunk_id": "chunk.test",
        "quote_or_summary": "The text explicitly states X.",
        "confidence": "high",
        "evidence_status": "source_supported",
    }
    base.update(kwargs)
    return base


def _make_rule(**kwargs) -> dict:
    base = {
        "id": "rule.test",
        "label": "Test rule",
        "description": "A rule grounded in evidence.",
        "domain": "RGPD",
        "severity": "medium",
        "confidence": "high",
        "evidence_status": "source_supported",
        "evidence": [_make_evidence()],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_empty_extraction_result_is_valid() -> None:
    result = ExtractionResult.model_validate({})
    assert result.rules == []
    assert result.concepts == []
    assert result.conditions == []
    assert result.actions == []


def test_valid_extraction_passes_schema_validation() -> None:
    payload = {
        "concepts": [
            {
                "id": "concept.personal_data",
                "label": "Personal data",
                "description": "Data related to an identifiable person.",
                "aliases": ["données personnelles"],
                "domain": "RGPD",
                "source_ids": ["src.test"],
            }
        ],
        "rules": [_make_rule()],
        "conditions": [
            {
                "id": "condition.health_data_present",
                "label": "Health data present",
                "description": "The project processes health data.",
                "detection_hint": "Look for health/medical data mentions.",
            }
        ],
        "actions": [
            {
                "id": "action.dpo_review",
                "label": "DPO review",
                "description": "Require DPO review.",
                "action_type": "governance",
            }
        ],
        "relations": [],
        "evidence": [],
    }
    result = ExtractionResult.model_validate(payload)
    assert len(result.rules) == 1
    assert result.rules[0].evidence_status == EvidenceStatus.source_supported


def test_rule_without_evidence_fails_for_non_manual_statuses() -> None:
    """Non-manual-seed rules require at least one evidence item."""
    for status in ("source_supported", "inferred"):
        with pytest.raises(ValidationError, match="evidence"):
            Rule(
                id="rule.bad",
                label="Bad rule",
                description="No evidence",
                domain="RGPD",
                severity=Severity.high,
                evidence_status=status,  # type: ignore[arg-type]
                evidence=[],
            )


def test_manual_seed_rule_without_evidence_is_allowed() -> None:
    """manual_seed_unverified rules may have empty evidence (KB seeds do not cite chunks)."""
    rule = Rule(
        id="rule.seed",
        label="Seeded rule",
        description="Seeded manually",
        domain="RGPD",
        severity=Severity.low,
        evidence_status=EvidenceStatus.manual_seed_unverified,
        evidence=[],
    )
    assert rule.evidence_status == EvidenceStatus.manual_seed_unverified


def test_knowledge_payload_rejects_source_supported_rule_without_evidence() -> None:
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
                        "evidence_status": "source_supported",
                        "evidence": [],
                    }
                ]
            }
        )


def test_inferred_rule_is_allowed_but_marked() -> None:
    rule = Rule.model_validate(
        _make_rule(
            evidence_status="inferred",
            evidence=[_make_evidence(evidence_status="inferred")],
        )
    )
    assert rule.evidence_status == EvidenceStatus.inferred
    assert rule.evidence[0].evidence_status == EvidenceStatus.inferred


def test_source_supported_rule_requires_evidence() -> None:
    """A source_supported rule must still carry at least one evidence item."""
    with pytest.raises(ValidationError):
        Rule.model_validate(
            _make_rule(evidence_status="source_supported", evidence=[])
        )


def test_evidence_string_confidence_is_coerced() -> None:
    ev = Evidence(
        source_id="s",
        chunk_id="c",
        quote_or_summary="Q",
        confidence="high",
    )
    assert ev.confidence == pytest.approx(0.9)

    ev2 = Evidence(
        source_id="s",
        chunk_id="c",
        quote_or_summary="Q",
        confidence="low",
    )
    assert ev2.confidence == pytest.approx(0.3)


def test_evidence_default_status_is_manual_seed_unverified() -> None:
    ev = Evidence(source_id="s", chunk_id="c", quote_or_summary="Q")
    assert ev.evidence_status == EvidenceStatus.manual_seed_unverified


def test_rule_default_status_is_manual_seed_unverified() -> None:
    data = _make_rule()
    del data["evidence_status"]
    rule = Rule.model_validate(data)
    assert rule.evidence_status == EvidenceStatus.manual_seed_unverified


# ---------------------------------------------------------------------------
# extract_knowledge helpers
# ---------------------------------------------------------------------------

def test_filter_rejected_removes_rejected_rules() -> None:
    from app.extract_knowledge import _filter_rejected

    payload = {
        "rules": [
            {"id": "rule.ok", "evidence_status": "source_supported",
             "evidence": [_make_evidence()]},
            {"id": "rule.bad", "evidence_status": "rejected"},
        ]
    }
    clean, rejected = _filter_rejected(payload)
    assert len(clean["rules"]) == 1
    assert clean["rules"][0]["id"] == "rule.ok"
    assert any(r["rejected_rule_id"] == "rule.bad" for r in rejected)


def test_parse_json_strips_markdown_fences() -> None:
    from app.extract_knowledge import _parse_json

    raw = '```json\n{"concepts": []}\n```'
    result = _parse_json(raw)
    assert result == {"concepts": []}


def test_parse_json_plain_json() -> None:
    from app.extract_knowledge import _parse_json

    raw = '{"rules": []}'
    assert _parse_json(raw) == {"rules": []}


def test_build_prompt_fills_template() -> None:
    from app.extract_knowledge import _build_prompt

    template = "Source: <<source_id>> Chunk: <<chunk_id>> Section: <<section_title>>\n<<chunk_text>>"
    chunk = {
        "source_id": "src.001",
        "chunk_id": "chunk.001",
        "section_title": "Article 5",
        "text": "Personal data shall be processed lawfully.",
    }
    prompt = _build_prompt(template, chunk)
    assert "src.001" in prompt
    assert "chunk.001" in prompt
    assert "Article 5" in prompt
    assert "Personal data shall be processed lawfully." in prompt


# ---------------------------------------------------------------------------
# extract_knowledge integration (dry-run via tmp chunks)
# ---------------------------------------------------------------------------

def test_dry_run_does_not_call_llm(tmp_path: Path, capsys) -> None:
    from app.extract_knowledge import extract_chunks

    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps(
            {
                "chunk_id": "chunk.001",
                "source_id": "src.001",
                "section_title": "Test",
                "text": "Some governance text.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "extracted"

    extract_chunks(
        chunks_path=chunks_file,
        output_dir=out_dir,
        model="gpt-4.1-mini",
        dry_run=True,
    )

    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    # No output JSON files created
    assert list(out_dir.glob("*.json")) == []


def test_invalid_llm_json_does_not_crash(tmp_path: Path) -> None:
    """LLM returning garbage JSON should log an error but not crash."""
    from app.extract_knowledge import extract_chunks

    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps(
            {
                "chunk_id": "chunk.001",
                "source_id": "src.001",
                "section_title": None,
                "text": "Some text.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "extracted"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value="not valid json {{"),
    ):
        extract_chunks(
            chunks_path=chunks_file,
            output_dir=out_dir,
            model="gpt-4.1-mini",
        )

    log_lines = [
        json.loads(l)
        for l in (out_dir / "extraction_log.jsonl").read_text().splitlines()
        if l.strip()
    ]
    assert log_lines[0]["status"] == "error"
    assert "JSON parse failed" in log_lines[0]["error"]


def test_valid_llm_output_saves_file(tmp_path: Path) -> None:
    from app.extract_knowledge import extract_chunks

    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps(
            {
                "chunk_id": "chunk.001",
                "source_id": "src.001",
                "section_title": "Art. 5",
                "text": "Personal data shall be adequate.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "extracted"

    llm_response = json.dumps(
        {
            "concepts": [],
            "rules": [
                {
                    "id": "rule.data_adequacy",
                    "label": "Data adequacy",
                    "description": "Personal data must be adequate.",
                    "domain": "RGPD",
                    "severity": "medium",
                    "confidence": "high",
                    "evidence_status": "source_supported",
                    "evidence": [
                        {
                            "source_id": "src.001",
                            "chunk_id": "chunk.001",
                            "quote_or_summary": "Personal data shall be adequate.",
                            "confidence": "high",
                            "evidence_status": "source_supported",
                        }
                    ],
                }
            ],
            "conditions": [],
            "actions": [],
            "relations": [],
            "evidence": [],
        }
    )

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=llm_response),
    ):
        extract_chunks(
            chunks_path=chunks_file,
            output_dir=out_dir,
            model="gpt-4.1-mini",
        )

    out_file = out_dir / "chunk.001.json"
    assert out_file.exists()
    saved = json.loads(out_file.read_text())
    assert len(saved["rules"]) == 1
    assert saved["rules"][0]["evidence_status"] == "source_supported"


def test_rejected_rules_are_not_saved(tmp_path: Path) -> None:
    from app.extract_knowledge import extract_chunks

    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps(
            {
                "chunk_id": "chunk.002",
                "source_id": "src.001",
                "section_title": None,
                "text": "Some text.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "extracted"

    llm_response = json.dumps(
        {
            "concepts": [],
            "rules": [
                {
                    "id": "rule.rejected",
                    "label": "Rejected rule",
                    "description": "This should be filtered out.",
                    "domain": "RGPD",
                    "severity": "low",
                    "confidence": "low",
                    "evidence_status": "rejected",
                    "evidence": [],
                }
            ],
            "conditions": [],
            "actions": [],
            "relations": [],
            "evidence": [],
        }
    )

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=llm_response),
    ):
        extract_chunks(
            chunks_path=chunks_file,
            output_dir=out_dir,
            model="gpt-4.1-mini",
        )

    out_file = out_dir / "chunk.002.json"
    assert out_file.exists()
    saved = json.loads(out_file.read_text())
    # The rejected rule had empty evidence and was stripped, so rules list is empty
    assert saved["rules"] == []


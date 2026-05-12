"""Tests for Phase 4.5: evidence consistency, rejected-rule logging,
review_extractions CLI, inspect_kb CLI, and fixture-based semantic tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.schemas import Evidence, EvidenceStatus, Rule, Severity


# ---------------------------------------------------------------------------
# Fixtures dir
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "extraction_chunks"


# ===========================================================================
# Task 1 — Evidence consistency validation
# ===========================================================================

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


def test_source_supported_rule_requires_source_supported_evidence_item() -> None:
    """source_supported rule with only inferred evidence must be rejected."""
    with pytest.raises(ValidationError, match="source_supported"):
        Rule.model_validate(
            _make_rule(
                evidence_status="source_supported",
                evidence=[_make_evidence(evidence_status="inferred")],
            )
        )


def test_source_supported_rule_with_mixed_evidence_passes() -> None:
    """source_supported rule with at least one source_supported evidence item is valid."""
    rule = Rule.model_validate(
        _make_rule(
            evidence=[
                _make_evidence(evidence_status="inferred"),
                _make_evidence(evidence_status="source_supported"),
            ]
        )
    )
    assert rule.evidence_status == EvidenceStatus.source_supported


def test_inferred_rule_with_inferred_evidence_is_valid() -> None:
    rule = Rule.model_validate(
        _make_rule(
            evidence_status="inferred",
            evidence=[_make_evidence(evidence_status="inferred")],
        )
    )
    assert rule.evidence_status == EvidenceStatus.inferred


def test_manual_seed_rule_with_no_evidence_is_allowed() -> None:
    """manual_seed_unverified rules may have empty evidence (KB seeds)."""
    rule = Rule.model_validate(
        _make_rule(evidence_status="manual_seed_unverified", evidence=[])
    )
    assert rule.evidence_status == EvidenceStatus.manual_seed_unverified


def test_inferred_rule_with_empty_evidence_fails() -> None:
    """Inferred rules still require at least one evidence item."""
    with pytest.raises(ValidationError):
        Rule.model_validate(
            _make_rule(evidence_status="inferred", evidence=[])
        )


# ===========================================================================
# Task 2 — Rejected-rule logging
# ===========================================================================

def test_filter_rejected_logs_rejected_status(tmp_path: Path) -> None:
    from app.extract_knowledge import _filter_rejected

    payload = {
        "rules": [
            {"id": "rule.ok", "evidence_status": "source_supported",
             "evidence": [_make_evidence()]},
            {"id": "rule.bad", "evidence_status": "rejected", "evidence": []},
        ]
    }
    chunk = {"chunk_id": "chunk.001", "source_id": "src.001"}
    clean, rejected = _filter_rejected(payload, chunk=chunk)
    assert len(clean["rules"]) == 1
    assert clean["rules"][0]["id"] == "rule.ok"
    assert len(rejected) == 1
    assert rejected[0]["rejected_rule_id"] == "rule.bad"
    assert rejected[0]["chunk_id"] == "chunk.001"
    assert rejected[0]["source_id"] == "src.001"
    assert "rejected" in rejected[0]["rejection_reason"]


def test_filter_rejected_logs_missing_source_evidence() -> None:
    from app.extract_knowledge import _filter_rejected

    payload = {
        "rules": [
            {
                "id": "rule.nosource",
                "evidence_status": "source_supported",
                "evidence": [_make_evidence(evidence_status="inferred")],
            }
        ]
    }
    chunk = {"chunk_id": "chunk.002", "source_id": "src.001"}
    clean, rejected = _filter_rejected(payload, chunk=chunk)
    assert len(clean["rules"]) == 0
    assert len(rejected) == 1
    assert "source_supported" in rejected[0]["rejection_reason"]


def test_rejected_rules_written_to_log(tmp_path: Path) -> None:
    """End-to-end: rejected rules appear in extraction_log.jsonl, not in output JSON."""
    from app.extract_knowledge import extract_chunks

    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps({
            "chunk_id": "chunk.rej",
            "source_id": "src.001",
            "section_title": None,
            "text": "Some text.",
        }) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "extracted"

    llm_response = json.dumps({
        "concepts": [],
        "rules": [
            {
                "id": "rule.accepted",
                "label": "Accepted",
                "description": "Good rule.",
                "domain": "RGPD",
                "severity": "medium",
                "confidence": "high",
                "evidence_status": "source_supported",
                "evidence": [_make_evidence(chunk_id="chunk.rej", source_id="src.001")],
            },
            {
                "id": "rule.noev",
                "label": "No evidence",
                "description": "Bad rule - no evidence.",
                "domain": "RGPD",
                "severity": "low",
                "evidence_status": "rejected",
                "evidence": [],
            },
        ],
        "conditions": [],
        "actions": [],
        "relations": [],
        "evidence": [],
    })

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=llm_response),
    ):
        extract_chunks(chunks_path=chunks_file, output_dir=out_dir, model="gpt-4.1-mini")

    # Accepted output only contains valid rule
    saved = json.loads((out_dir / "chunk.rej.json").read_text())
    assert len(saved["rules"]) == 1
    assert saved["rules"][0]["id"] == "rule.accepted"

    # Log contains the rejected entry
    log_entries = [
        json.loads(l)
        for l in (out_dir / "extraction_log.jsonl").read_text().splitlines()
        if l.strip()
    ]
    rejected = [e for e in log_entries if e.get("status") == "rejected_rule"]
    assert len(rejected) == 1
    assert rejected[0]["rejected_rule_id"] == "rule.noev"
    assert rejected[0]["chunk_id"] == "chunk.rej"
    assert rejected[0]["source_id"] == "src.001"
    assert "rejection_reason" in rejected[0]
    assert "evidence_status" in rejected[0]
    assert "timestamp" in rejected[0]


# ===========================================================================
# Task 3 — review_extractions CLI
# ===========================================================================

def _make_extracted_dir(tmp_path: Path, rules: list[dict], concepts: list[dict] | None = None) -> Path:
    out_dir = tmp_path / "extracted"
    out_dir.mkdir()
    data = {
        "concepts": concepts or [],
        "rules": rules,
        "conditions": [],
        "actions": [],
        "relations": [],
        "evidence": [],
    }
    (out_dir / "chunk.001.json").write_text(json.dumps(data), encoding="utf-8")
    return out_dir


def test_review_extractions_runs(tmp_path: Path, capsys) -> None:
    from app.review_extractions import review

    rules = [
        {"id": "rule.a", "label": "A", "domain": "RGPD",
         "evidence_status": "source_supported",
         "evidence": [_make_evidence()]},
        {"id": "rule.b", "label": "B", "domain": "RGPD",
         "evidence_status": "inferred",
         "evidence": [_make_evidence(evidence_status="inferred")]},
    ]
    out_dir = _make_extracted_dir(tmp_path, rules)
    review(extracted_dir=out_dir)
    captured = capsys.readouterr()
    assert "EXTRACTION REVIEW" in captured.out
    assert "source_supported" in captured.out
    assert "inferred" in captured.out


def test_review_extractions_detects_duplicate_labels(tmp_path: Path, capsys) -> None:
    from app.review_extractions import review

    rules = [
        {"id": "rule.a1", "label": "Finality rule", "domain": "RGPD",
         "evidence_status": "source_supported",
         "evidence": [_make_evidence()]},
        {"id": "rule.a2", "label": "Finality rule", "domain": "RGPD",
         "evidence_status": "inferred",
         "evidence": [_make_evidence(evidence_status="inferred")]},
    ]
    out_dir = _make_extracted_dir(tmp_path, rules)
    review(extracted_dir=out_dir)
    captured = capsys.readouterr()
    assert "finality rule" in captured.out.lower() or "Duplicate" in captured.out


def test_review_extractions_detects_missing_source_evidence(tmp_path: Path, capsys) -> None:
    from app.review_extractions import review

    rules = [
        {
            "id": "rule.weak",
            "label": "Weak rule",
            "domain": "RGPD",
            "evidence_status": "source_supported",
            "evidence": [_make_evidence(evidence_status="inferred")],
        }
    ]
    out_dir = _make_extracted_dir(tmp_path, rules)
    review(extracted_dir=out_dir)
    captured = capsys.readouterr()
    assert "rule.weak" in captured.out or "missing source evidence" in captured.out.lower()


def test_review_extractions_domain_filter(tmp_path: Path, capsys) -> None:
    from app.review_extractions import review

    rules = [
        {"id": "rule.a", "label": "A", "domain": "RGPD",
         "evidence_status": "source_supported",
         "evidence": [_make_evidence()]},
        {"id": "rule.b", "label": "B", "domain": "HDS",
         "evidence_status": "source_supported",
         "evidence": [_make_evidence()]},
    ]
    out_dir = _make_extracted_dir(tmp_path, rules)
    review(extracted_dir=out_dir, domain="RGPD")
    captured = capsys.readouterr()
    assert "Rules matching filter: 1" in captured.out


def test_review_extractions_rejected_count_from_log(tmp_path: Path, capsys) -> None:
    from app.review_extractions import review

    out_dir = tmp_path / "extracted"
    out_dir.mkdir()
    (out_dir / "chunk.001.json").write_text(
        json.dumps({"concepts": [], "rules": [], "conditions": [], "actions": []}),
        encoding="utf-8",
    )
    # Write a fake rejected log entry
    log_entry = {
        "status": "rejected_rule",
        "chunk_id": "chunk.001",
        "source_id": "src.001",
        "rejected_rule_id": "rule.x",
        "rejected_rule_label": "Bad rule",
        "rejection_reason": "evidence_status=rejected",
        "evidence_status": "rejected",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    (out_dir / "extraction_log.jsonl").write_text(
        json.dumps(log_entry) + "\n", encoding="utf-8"
    )
    review(extracted_dir=out_dir)
    captured = capsys.readouterr()
    assert "Rejected candidates" in captured.out
    assert "1" in captured.out


# ===========================================================================
# Task 4 — inspect_kb CLI
# ===========================================================================

def _make_kb(tmp_path: Path, rules: list[dict] | None = None, concepts: list[dict] | None = None) -> Path:
    kb = {
        "concepts": concepts or [{"id": "c.1", "label": "Personal data", "domain": "RGPD"}],
        "rules": rules or [],
        "conditions": [{"id": "cond.1", "label": "Health data present"}],
        "actions": [{"id": "act.1", "label": "DPO review", "action_type": "governance"}],
        "relations": [],
        "evidence": [],
    }
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    return kb_path


def test_inspect_kb_runs(tmp_path: Path, capsys) -> None:
    from app.inspect_kb import inspect

    rules = [
        {
            "id": "rule.a",
            "label": "DPO required",
            "domain": "RGPD",
            "severity": "high",
            "evidence_status": "source_supported",
            "evidence": [_make_evidence()],
            "trigger_conditions": ["cond.1"],
            "recommended_actions": ["act.1"],
        }
    ]
    kb_path = _make_kb(tmp_path, rules=rules)
    inspect(kb_path)
    captured = capsys.readouterr()
    assert "KB INSPECTION" in captured.out
    assert "1" in captured.out  # counts


def test_inspect_kb_detects_duplicate_ids(tmp_path: Path, capsys) -> None:
    from app.inspect_kb import inspect

    rules = [
        {"id": "rule.dup", "label": "A", "domain": "RGPD", "severity": "low",
         "evidence_status": "source_supported", "evidence": [_make_evidence()],
         "trigger_conditions": ["c"], "recommended_actions": ["a"]},
        {"id": "rule.dup", "label": "B", "domain": "RGPD", "severity": "low",
         "evidence_status": "inferred", "evidence": [_make_evidence(evidence_status="inferred")],
         "trigger_conditions": [], "recommended_actions": []},
    ]
    kb_path = _make_kb(tmp_path, rules=rules)
    inspect(kb_path)
    captured = capsys.readouterr()
    assert "rule.dup" in captured.out
    assert "Duplicate" in captured.out


def test_inspect_kb_reports_missing_actions(tmp_path: Path, capsys) -> None:
    from app.inspect_kb import inspect

    rules = [
        {"id": "rule.noact", "label": "No action", "domain": "RGPD", "severity": "medium",
         "evidence_status": "manual_seed_unverified", "evidence": [],
         "trigger_conditions": ["cond.1"], "recommended_actions": []},
    ]
    kb_path = _make_kb(tmp_path, rules=rules)
    inspect(kb_path)
    captured = capsys.readouterr()
    assert "rule.noact" in captured.out
    assert "missing recommended_actions" in captured.out.lower()


def test_inspect_kb_reports_manual_unverified(tmp_path: Path, capsys) -> None:
    from app.inspect_kb import inspect

    rules = [
        {"id": "rule.seed", "label": "Seeded rule", "domain": "RGPD", "severity": "low",
         "evidence_status": "manual_seed_unverified", "evidence": [],
         "trigger_conditions": ["c"], "recommended_actions": ["a"]},
    ]
    kb_path = _make_kb(tmp_path, rules=rules)
    inspect(kb_path)
    captured = capsys.readouterr()
    assert "rule.seed" in captured.out
    assert "manual" in captured.out.lower()


# ===========================================================================
# Task 5 — Semantic extraction fixtures
# ===========================================================================

def _llm_response_finality() -> str:
    """Simulated LLM response for the finality chunk."""
    return json.dumps({
        "concepts": [
            {
                "id": "concept.purpose_limitation",
                "label": "Purpose limitation",
                "description": "Personal data collected for specified purposes only.",
                "aliases": ["limitation des finalités"],
                "domain": "RGPD",
                "source_ids": ["src.gdpr.art5"],
            }
        ],
        "rules": [
            {
                "id": "rule.purpose_limitation",
                "label": "Purpose limitation",
                "description": "Data must not be processed beyond its stated purpose.",
                "domain": "RGPD",
                "severity": "high",
                "confidence": "high",
                "evidence_status": "source_supported",
                "trigger_conditions": [],
                "recommended_actions": [],
                "evidence": [
                    {
                        "source_id": "src.gdpr.art5",
                        "chunk_id": "chunk.finality.001",
                        "quote_or_summary": "not further processed in a manner incompatible with those purposes",
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
    })


def _llm_response_minimization_no_dpo() -> str:
    """Simulated LLM response for the data minimization chunk — no DPO rule invented."""
    return json.dumps({
        "concepts": [
            {
                "id": "concept.data_minimisation",
                "label": "Data minimisation",
                "description": "Only collect data adequate, relevant and limited to purpose.",
                "aliases": ["minimisation des données"],
                "domain": "RGPD",
                "source_ids": ["src.gdpr.art5"],
            }
        ],
        "rules": [
            {
                "id": "rule.data_minimisation",
                "label": "Data minimisation",
                "description": "Collect only necessary data.",
                "domain": "RGPD",
                "severity": "high",
                "confidence": "high",
                "evidence_status": "source_supported",
                "trigger_conditions": [],
                "recommended_actions": [],
                "evidence": [
                    {
                        "source_id": "src.gdpr.art5",
                        "chunk_id": "chunk.minimization.001",
                        "quote_or_summary": "adequate, relevant and limited to what is necessary",
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
    })


def _llm_response_empty() -> str:
    """Simulated LLM response for an irrelevant chunk — empty arrays."""
    return json.dumps({
        "concepts": [],
        "rules": [],
        "conditions": [],
        "actions": [],
        "relations": [],
        "evidence": [],
    })


def _llm_response_inferred() -> str:
    """Simulated LLM response with an inferred rule (not source_supported)."""
    return json.dumps({
        "concepts": [],
        "rules": [
            {
                "id": "rule.special_category_inferred",
                "label": "Special category data requires explicit consent",
                "description": "Inferred from reading Article 9.",
                "domain": "RGPD",
                "severity": "high",
                "confidence": "medium",
                "evidence_status": "inferred",
                "trigger_conditions": [],
                "recommended_actions": [],
                "evidence": [
                    {
                        "source_id": "src.internal_note",
                        "chunk_id": "chunk.inferred.001",
                        "quote_or_summary": "likely requires explicit consent (interpretation, not direct quote)",
                        "confidence": "medium",
                        "evidence_status": "inferred",
                    }
                ],
            }
        ],
        "conditions": [],
        "actions": [],
        "relations": [],
        "evidence": [],
    })


def test_fixture_finality_chunk_extracts_finality_concept(tmp_path: Path) -> None:
    """A finality chunk extracts a finality-related concept or rule."""
    from app.extract_knowledge import extract_chunks

    chunks_file = FIXTURES / "chunks.jsonl"
    out_dir = tmp_path / "extracted"

    # Use only the finality chunk
    finality_chunks = [
        line for line in chunks_file.read_text(encoding="utf-8").splitlines()
        if "chunk.finality" in line
    ]
    test_chunks = tmp_path / "finality.jsonl"
    test_chunks.write_text("\n".join(finality_chunks) + "\n", encoding="utf-8")

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=_llm_response_finality()),
    ):
        extract_chunks(chunks_path=test_chunks, output_dir=out_dir, model="gpt-4.1-mini")

    saved = json.loads((out_dir / "chunk.finality.001.json").read_text())
    concept_labels = [c["label"].lower() for c in saved.get("concepts", [])]
    rule_labels = [r["label"].lower() for r in saved.get("rules", [])]
    assert any("purpose" in l or "finalit" in l or "limitation" in l for l in concept_labels + rule_labels)


def test_fixture_minimization_does_not_invent_dpo_rule(tmp_path: Path) -> None:
    """A data minimization chunk does not invent unrelated DPO requirements."""
    from app.extract_knowledge import extract_chunks

    chunks_file = FIXTURES / "chunks.jsonl"
    minimization_chunks = [
        line for line in chunks_file.read_text(encoding="utf-8").splitlines()
        if "chunk.minimization" in line
    ]
    test_chunks = tmp_path / "minimization.jsonl"
    test_chunks.write_text("\n".join(minimization_chunks) + "\n", encoding="utf-8")

    out_dir = tmp_path / "extracted"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=_llm_response_minimization_no_dpo()),
    ):
        extract_chunks(chunks_path=test_chunks, output_dir=out_dir, model="gpt-4.1-mini")

    saved = json.loads((out_dir / "chunk.minimization.001.json").read_text())
    rule_labels = [r["label"].lower() for r in saved.get("rules", [])]
    # No DPO-unrelated rule should appear
    assert not any("dpo" in l and "minimis" not in l for l in rule_labels)


def test_fixture_irrelevant_chunk_returns_empty(tmp_path: Path) -> None:
    """An irrelevant text chunk returns empty arrays."""
    from app.extract_knowledge import extract_chunks

    chunks_file = FIXTURES / "chunks.jsonl"
    irrelevant_chunks = [
        line for line in chunks_file.read_text(encoding="utf-8").splitlines()
        if "chunk.irrelevant" in line
    ]
    test_chunks = tmp_path / "irrelevant.jsonl"
    test_chunks.write_text("\n".join(irrelevant_chunks) + "\n", encoding="utf-8")

    out_dir = tmp_path / "extracted"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=_llm_response_empty()),
    ):
        extract_chunks(chunks_path=test_chunks, output_dir=out_dir, model="gpt-4.1-mini")

    saved = json.loads((out_dir / "chunk.irrelevant.001.json").read_text())
    assert saved.get("rules", []) == []
    assert saved.get("concepts", []) == []


def test_fixture_source_supported_rule_cites_chunk(tmp_path: Path) -> None:
    """A source_supported rule must cite the chunk_id and source_id in its evidence."""
    from app.extract_knowledge import extract_chunks

    chunks_file = FIXTURES / "chunks.jsonl"
    finality_chunks = [
        line for line in chunks_file.read_text(encoding="utf-8").splitlines()
        if "chunk.finality" in line
    ]
    test_chunks = tmp_path / "finality.jsonl"
    test_chunks.write_text("\n".join(finality_chunks) + "\n", encoding="utf-8")

    out_dir = tmp_path / "extracted"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=_llm_response_finality()),
    ):
        extract_chunks(chunks_path=test_chunks, output_dir=out_dir, model="gpt-4.1-mini")

    saved = json.loads((out_dir / "chunk.finality.001.json").read_text())
    for rule in saved.get("rules", []):
        if rule.get("evidence_status") == "source_supported":
            evidence = rule.get("evidence", [])
            assert any(
                e.get("chunk_id") == "chunk.finality.001" and e.get("source_id") == "src.gdpr.art5"
                for e in evidence
            ), f"Rule {rule['id']} does not cite chunk/source in evidence"


def test_fixture_inferred_rule_not_source_supported(tmp_path: Path) -> None:
    """An inferred rule is saved as inferred, not upgraded to source_supported."""
    from app.extract_knowledge import extract_chunks

    chunks_file = FIXTURES / "chunks.jsonl"
    inferred_chunks = [
        line for line in chunks_file.read_text(encoding="utf-8").splitlines()
        if "chunk.inferred" in line
    ]
    test_chunks = tmp_path / "inferred.jsonl"
    test_chunks.write_text("\n".join(inferred_chunks) + "\n", encoding="utf-8")

    out_dir = tmp_path / "extracted"

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("app.extract_knowledge._call_llm", return_value=_llm_response_inferred()),
    ):
        extract_chunks(chunks_path=test_chunks, output_dir=out_dir, model="gpt-4.1-mini")

    saved = json.loads((out_dir / "chunk.inferred.001.json").read_text())
    for rule in saved.get("rules", []):
        assert rule.get("evidence_status") != "source_supported", (
            f"Rule {rule['id']} was incorrectly upgraded to source_supported"
        )


# ===========================================================================
# Task 6 — Normalize KB strengthening
# ===========================================================================

def _base_kb(rules: list[dict] | None = None, concepts: list[dict] | None = None) -> dict:
    return {
        "concepts": concepts or [],
        "rules": rules or [],
        "conditions": [],
        "actions": [],
        "relations": [],
        "evidence": [],
    }


def test_normalize_kb_preserves_aliases_on_merge(tmp_path: Path) -> None:
    from app.normalize_kb import normalize_kb

    concept = {
        "id": "c.pdp",
        "label": "Personal data",
        "description": "desc",
        "aliases": ["données personnelles"],
        "domain": "RGPD",
        "source_ids": ["src.1"],
    }
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(_base_kb(concepts=[concept])), encoding="utf-8")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    # Same concept with an additional alias
    concept2 = dict(concept)
    concept2["aliases"] = ["données personnelles", "personal data"]
    (extracted_dir / "chunk.001.json").write_text(
        json.dumps({"concepts": [concept2], "rules": [], "conditions": [], "actions": []}),
        encoding="utf-8",
    )

    out_path = tmp_path / "kb_out.json"
    sqlite_path = tmp_path / "kb.sqlite"
    normalize_kb(kb_path, out_path, sqlite_path, extracted_dir=extracted_dir)

    result = json.loads(out_path.read_text())
    merged_concept = next(c for c in result["concepts"] if c["id"] == "c.pdp")
    assert "données personnelles" in merged_concept["aliases"]
    assert "personal data" in merged_concept["aliases"]


def test_normalize_kb_prefers_source_supported_status(tmp_path: Path) -> None:
    from app.normalize_kb import normalize_kb

    rule = {
        "id": "rule.r1",
        "label": "Rule 1",
        "description": "desc",
        "domain": "RGPD",
        "severity": "medium",
        "evidence_status": "manual_seed_unverified",
        "evidence": [],
    }
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(_base_kb(rules=[rule])), encoding="utf-8")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    rule_upgraded = dict(rule)
    rule_upgraded["evidence_status"] = "source_supported"
    rule_upgraded["evidence"] = [_make_evidence()]
    (extracted_dir / "chunk.001.json").write_text(
        json.dumps({"concepts": [], "rules": [rule_upgraded], "conditions": [], "actions": []}),
        encoding="utf-8",
    )

    out_path = tmp_path / "kb_out.json"
    sqlite_path = tmp_path / "kb.sqlite"
    normalize_kb(kb_path, out_path, sqlite_path, extracted_dir=extracted_dir)

    result = json.loads(out_path.read_text())
    merged_rule = next(r for r in result["rules"] if r["id"] == "rule.r1")
    assert merged_rule["evidence_status"] == "source_supported"


def test_normalize_kb_preserves_manual_seed_provenance(tmp_path: Path) -> None:
    from app.normalize_kb import normalize_kb

    seed_evidence = {
        "source_id": "src.manual",
        "chunk_id": "chunk.manual",
        "quote_or_summary": "Manual seed evidence",
        "evidence_status": "manual_seed_unverified",
    }
    rule = {
        "id": "rule.r2",
        "label": "Rule 2",
        "description": "desc",
        "domain": "RGPD",
        "severity": "medium",
        "evidence_status": "manual_seed_unverified",
        "evidence": [seed_evidence],
    }
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(_base_kb(rules=[rule])), encoding="utf-8")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    source_evidence = _make_evidence(quote_or_summary="Source-backed evidence from doc")
    rule_upgraded = dict(rule)
    rule_upgraded["evidence_status"] = "source_supported"
    rule_upgraded["evidence"] = [source_evidence]
    (extracted_dir / "chunk.001.json").write_text(
        json.dumps({"concepts": [], "rules": [rule_upgraded], "conditions": [], "actions": []}),
        encoding="utf-8",
    )

    out_path = tmp_path / "kb_out.json"
    sqlite_path = tmp_path / "kb.sqlite"
    normalize_kb(kb_path, out_path, sqlite_path, extracted_dir=extracted_dir)

    result = json.loads(out_path.read_text())
    merged_rule = next(r for r in result["rules"] if r["id"] == "rule.r2")
    # Both manual seed and source evidence should be preserved
    quotes = {e["quote_or_summary"] for e in merged_rule["evidence"]}
    assert "Manual seed evidence" in quotes
    assert "Source-backed evidence from doc" in quotes


def test_normalize_kb_does_not_duplicate_evidence(tmp_path: Path) -> None:
    from app.normalize_kb import normalize_kb

    evidence_item = _make_evidence(quote_or_summary="Same quote")
    rule = {
        "id": "rule.r3",
        "label": "Rule 3",
        "description": "desc",
        "domain": "RGPD",
        "severity": "medium",
        "evidence_status": "source_supported",
        "evidence": [evidence_item],
    }
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(_base_kb(rules=[rule])), encoding="utf-8")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    # Same evidence item appears again in extracted
    (extracted_dir / "chunk.001.json").write_text(
        json.dumps({"concepts": [], "rules": [rule], "conditions": [], "actions": []}),
        encoding="utf-8",
    )

    out_path = tmp_path / "kb_out.json"
    sqlite_path = tmp_path / "kb.sqlite"
    normalize_kb(kb_path, out_path, sqlite_path, extracted_dir=extracted_dir)

    result = json.loads(out_path.read_text())
    merged_rule = next(r for r in result["rules"] if r["id"] == "rule.r3")
    quotes = [e["quote_or_summary"] for e in merged_rule["evidence"]]
    # No duplicate quotes
    assert quotes.count("Same quote") == 1

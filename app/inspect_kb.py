from __future__ import annotations

"""
KB inspection command.

Usage:
    python -m app.inspect_kb --kb data/kb/kb.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _duplicate_ids(items: list[dict]) -> list[str]:
    counts = Counter(item.get("id") for item in items if item.get("id"))
    return sorted(iid for iid, cnt in counts.items() if cnt > 1)


def _rules_missing_actions(rules: list[dict]) -> list[dict]:
    return [r for r in rules if not r.get("recommended_actions")]


def _rules_missing_conditions(rules: list[dict]) -> list[dict]:
    return [r for r in rules if not r.get("trigger_conditions")]


def _rules_with_multiple_evidence(rules: list[dict]) -> list[dict]:
    return [r for r in rules if len(r.get("evidence", [])) > 1]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def inspect(kb_path: Path) -> None:
    try:
        payload = json.loads(kb_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read KB: {exc}")
        raise SystemExit(1)

    concepts = payload.get("concepts", [])
    rules = payload.get("rules", [])
    conditions = payload.get("conditions", [])
    actions = payload.get("actions", [])
    relations = payload.get("relations", [])

    # Evidence status distribution for rules
    status_counter: Counter[str] = Counter(
        r.get("evidence_status", "unknown") for r in rules
    )

    # Rules by domain
    domain_counter: Counter[str] = Counter(r.get("domain", "unknown") for r in rules)

    # High-severity rules
    high_severity = [r for r in rules if r.get("severity") == "high"]

    # Manual/unverified rules
    manual_rules = [
        r for r in rules if r.get("evidence_status") == "manual_seed_unverified"
    ]

    # Duplicate IDs
    dup_concept_ids = _duplicate_ids(concepts)
    dup_rule_ids = _duplicate_ids(rules)
    dup_condition_ids = _duplicate_ids(conditions)
    dup_action_ids = _duplicate_ids(actions)

    # Missing recommended_actions / trigger_conditions
    missing_actions = _rules_missing_actions(rules)
    missing_conditions = _rules_missing_conditions(rules)

    # Rules with multiple evidence items
    multi_evidence = _rules_with_multiple_evidence(rules)

    # Source-supported rules
    source_supported = [r for r in rules if r.get("evidence_status") == "source_supported"]

    # ---- Print ----
    print("=" * 60)
    print("KB INSPECTION")
    print(f"  Source: {kb_path}")
    print("=" * 60)
    print(f"  Concepts           : {len(concepts)}")
    print(f"  Rules              : {len(rules)}")
    print(f"  Conditions         : {len(conditions)}")
    print(f"  Actions            : {len(actions)}")
    print(f"  Relations          : {len(relations)}")
    print()
    print("  Evidence status distribution (rules):")
    for status, cnt in sorted(status_counter.items(), key=lambda x: x[1], reverse=True):
        print(f"    {status:<30} {cnt}")
    print()
    print("  Rules by domain:")
    for domain, cnt in sorted(domain_counter.items(), key=lambda x: x[1], reverse=True):
        print(f"    {domain:<30} {cnt}")
    print()
    print(f"  High-severity rules        : {len(high_severity)}")
    for r in high_severity:
        print(f"    [{r.get('evidence_status', '?')}] {r.get('id')} — {r.get('label')}")
    print()
    print(f"  Manual/unverified rules    : {len(manual_rules)}")
    for r in manual_rules:
        print(f"    {r.get('id')} — {r.get('label')}")
    print()
    print(f"  Rules with multiple evidence items: {len(multi_evidence)}")
    for r in multi_evidence:
        print(f"    {r.get('id')} ({len(r.get('evidence', []))} items)")
    print()
    # Duplicate IDs
    any_dups = dup_concept_ids or dup_rule_ids or dup_condition_ids or dup_action_ids
    if any_dups:
        print("  ⚠  Duplicate IDs detected:")
        for iid in dup_concept_ids:
            print(f"    concept:    {iid}")
        for iid in dup_rule_ids:
            print(f"    rule:       {iid}")
        for iid in dup_condition_ids:
            print(f"    condition:  {iid}")
        for iid in dup_action_ids:
            print(f"    action:     {iid}")
    else:
        print("  ✓  No duplicate IDs")
    print()
    print(f"  Rules missing recommended_actions : {len(missing_actions)}")
    for r in missing_actions:
        print(f"    {r.get('id')} — {r.get('label')}")
    print()
    print(f"  Rules missing trigger_conditions  : {len(missing_conditions)}")
    for r in missing_conditions:
        print(f"    {r.get('id')} — {r.get('label')}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a normalized KB JSON file.")
    parser.add_argument(
        "--kb",
        type=Path,
        default=Path("data/kb/kb.json"),
        help="Path to the KB JSON file.",
    )
    args = parser.parse_args()

    if not args.kb.exists():
        print(f"ERROR: KB file not found: {args.kb}")
        raise SystemExit(1)

    inspect(args.kb)


if __name__ == "__main__":
    main()

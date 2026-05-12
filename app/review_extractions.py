from __future__ import annotations

"""
Extraction quality review command.

Usage:
    python -m app.review_extractions --extracted-dir data/extracted

Optional flags:
    --domain RGPD
    --status source_supported
    --show-rules
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def _load_extracted_files(extracted_dir: Path) -> tuple[list[dict], list[dict]]:
    """Return (rules, concepts) collected from all per-chunk JSON files (excluding log)."""
    rules: list[dict] = []
    concepts: list[dict] = []
    for f in sorted(extracted_dir.glob("*.json")):
        if f.name == "extraction_log.jsonl":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rules.extend(data.get("rules", []))
        concepts.extend(data.get("concepts", []))
    return rules, concepts


def _load_log(extracted_dir: Path) -> list[dict]:
    log_path = extracted_dir / "extraction_log.jsonl"
    if not log_path.exists():
        return []
    entries: list[dict] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _filter_items(
    items: list[dict],
    domain: str | None = None,
    status: str | None = None,
) -> list[dict]:
    result = items
    if domain:
        result = [r for r in result if r.get("domain", "").lower() == domain.lower()]
    if status:
        result = [r for r in result if r.get("evidence_status") == status]
    return result


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _duplicate_labels(rules: list[dict]) -> list[str]:
    counts = Counter(r.get("label", "").lower().strip() for r in rules)
    return sorted(label for label, cnt in counts.items() if cnt > 1 and label)


def _rules_missing_source_evidence(rules: list[dict]) -> list[dict]:
    """Source-supported rules that have no source_supported evidence item."""
    result = []
    for r in rules:
        if r.get("evidence_status") != "source_supported":
            continue
        evidence = r.get("evidence", [])
        has_source_ev = any(
            e.get("evidence_status") == "source_supported" for e in evidence
        )
        if not has_source_ev:
            result.append(r)
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def review(
    extracted_dir: Path,
    domain: str | None = None,
    status: str | None = None,
    show_rules: bool = False,
) -> None:
    json_files = [f for f in extracted_dir.glob("*.json") if f.name != "extraction_log.jsonl"]
    n_files = len(json_files)

    all_rules, all_concepts = _load_extracted_files(extracted_dir)
    log_entries = _load_log(extracted_dir)

    rules = _filter_items(all_rules, domain=domain, status=status)
    concepts = _filter_items(all_concepts, domain=domain, status=None)

    # Status breakdown
    status_counter: Counter[str] = Counter(r.get("evidence_status", "unknown") for r in all_rules)
    n_source_supported = status_counter.get("source_supported", 0)
    n_inferred = status_counter.get("inferred", 0)
    n_manual = status_counter.get("manual_seed_unverified", 0)

    # Rejected candidates from log
    n_rejected_candidates = sum(1 for e in log_entries if e.get("status") == "rejected_rule")

    # Domain breakdown
    domain_counter: Counter[str] = Counter(r.get("domain", "unknown") for r in all_rules)
    top_domains = domain_counter.most_common(5)

    # Quality warnings
    missing_ev = _rules_missing_source_evidence(all_rules)
    dup_labels = _duplicate_labels(all_rules)

    # ---- Print ----
    print("=" * 60)
    print("EXTRACTION REVIEW")
    if domain or status:
        print(f"  Filter  — domain: {domain or 'all'}, status: {status or 'all'}")
    print("=" * 60)
    print(f"  Extraction files     : {n_files}")
    print(f"  Concepts             : {len(all_concepts)}")
    print(f"  Rules (total)        : {len(all_rules)}")
    print(f"    source_supported   : {n_source_supported}")
    print(f"    inferred           : {n_inferred}")
    print(f"    manual_seed_unver. : {n_manual}")
    if n_rejected_candidates:
        print(f"  Rejected candidates  : {n_rejected_candidates}  (from log)")
    else:
        print(f"  Rejected candidates  : 0")
    print()
    print("  Top domains:")
    for d, cnt in top_domains:
        print(f"    {d:<30} {cnt} rule(s)")
    if missing_ev:
        print()
        print(f"  ⚠  Rules marked source_supported but missing source evidence: {len(missing_ev)}")
        for r in missing_ev:
            print(f"       {r.get('id')} — {r.get('label')}")
    if dup_labels:
        print()
        print(f"  ⚠  Duplicate-looking rule labels ({len(dup_labels)}):")
        for label in dup_labels:
            print(f"       {label!r}")
    if domain or status:
        print()
        print(f"  Rules matching filter: {len(rules)}")
        print(f"  Concepts matching filter: {len(concepts)}")
    if show_rules:
        print()
        print("  Rules:")
        display_rules = rules if (domain or status) else all_rules
        for r in display_rules:
            ev_status = r.get("evidence_status", "?")
            print(f"    [{ev_status}] {r.get('id')} — {r.get('label')}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review extraction quality from per-chunk JSON outputs."
    )
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        default=Path("data/extracted"),
        help="Directory containing per-chunk JSON files and extraction_log.jsonl.",
    )
    parser.add_argument("--domain", default=None, help="Filter by domain (e.g. RGPD).")
    parser.add_argument(
        "--status",
        default=None,
        help="Filter by evidence_status (e.g. source_supported).",
    )
    parser.add_argument(
        "--show-rules",
        action="store_true",
        help="Print individual rules in output.",
    )
    args = parser.parse_args()

    if not args.extracted_dir.exists():
        print(f"ERROR: directory not found: {args.extracted_dir}")
        raise SystemExit(1)

    review(
        extracted_dir=args.extracted_dir,
        domain=args.domain,
        status=args.status,
        show_rules=args.show_rules,
    )


if __name__ == "__main__":
    main()

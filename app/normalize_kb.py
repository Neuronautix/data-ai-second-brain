from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.schemas import EvidenceStatus


# ---------------------------------------------------------------------------
# Deduplication / merging helpers
# ---------------------------------------------------------------------------

_EVIDENCE_STATUS_PRIORITY = {
    EvidenceStatus.source_supported.value: 0,
    EvidenceStatus.inferred.value: 1,
    EvidenceStatus.manual_seed_unverified.value: 2,
    EvidenceStatus.rejected.value: 3,
}


def _dedupe_by_id(items: list[dict]) -> list[dict]:
    """Merge items with the same id, preserving list fields and best evidence_status."""
    seen: dict[str, dict] = {}
    for item in items:
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id not in seen:
            seen[item_id] = dict(item)
        else:
            merged = seen[item_id]
            for key, value in item.items():
                if isinstance(value, list):
                    existing = merged.get(key, [])
                    # Merge lists; for evidence lists dedupe by quote
                    if key == "evidence":
                        quotes = {e.get("quote_or_summary") for e in existing}
                        for ev in value:
                            if ev.get("quote_or_summary") not in quotes:
                                existing.append(ev)
                                quotes.add(ev.get("quote_or_summary"))
                        merged[key] = existing
                    else:
                        merged[key] = list(dict.fromkeys(existing + value))
            # Keep the best (highest priority) evidence_status
            current_status = merged.get("evidence_status", EvidenceStatus.manual_seed_unverified.value)
            incoming_status = item.get("evidence_status", EvidenceStatus.manual_seed_unverified.value)
            if _EVIDENCE_STATUS_PRIORITY.get(incoming_status, 99) < _EVIDENCE_STATUS_PRIORITY.get(current_status, 99):
                merged["evidence_status"] = incoming_status
    return list(seen.values())


def _load_extracted_dir(extracted_dir: Path) -> dict:
    """Load all per-chunk JSON files from data/extracted/ and merge them."""
    merged: dict[str, list] = {
        "concepts": [],
        "rules": [],
        "conditions": [],
        "actions": [],
        "relations": [],
        "evidence": [],
    }
    for json_file in sorted(extracted_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in merged:
            merged[key].extend(data.get(key, []))
    return merged


def _merge_payloads(base: dict, extracted: dict) -> dict:
    """Merge extracted into base, giving priority to source_supported items."""
    result: dict[str, list] = {}
    for key in ("concepts", "rules", "conditions", "actions", "relations", "evidence"):
        combined = base.get(key, []) + extracted.get(key, [])
        if key in ("concepts", "rules", "conditions", "actions"):
            result[key] = _dedupe_by_id(combined)
        else:
            result[key] = combined
    # Preserve any top-level keys from base not covered above
    for key in base:
        if key not in result:
            result[key] = base[key]
    return result


# ---------------------------------------------------------------------------
# SQLite snapshot
# ---------------------------------------------------------------------------

def _write_sqlite(payload: dict, sqlite_path: Path) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS concepts;
        DROP TABLE IF EXISTS rules;
        DROP TABLE IF EXISTS actions;
        DROP TABLE IF EXISTS conditions;

        CREATE TABLE concepts (id TEXT PRIMARY KEY, label TEXT, domain TEXT, json TEXT NOT NULL);
        CREATE TABLE rules (id TEXT PRIMARY KEY, label TEXT, severity TEXT, evidence_status TEXT, json TEXT NOT NULL);
        CREATE TABLE actions (id TEXT PRIMARY KEY, label TEXT, action_type TEXT, json TEXT NOT NULL);
        CREATE TABLE conditions (id TEXT PRIMARY KEY, label TEXT, json TEXT NOT NULL);
        """
    )

    for c in payload.get("concepts", []):
        cur.execute(
            "INSERT INTO concepts(id,label,domain,json) VALUES (?,?,?,?)",
            (c.get("id"), c.get("label"), c.get("domain"), json.dumps(c, ensure_ascii=False)),
        )
    for r in payload.get("rules", []):
        cur.execute(
            "INSERT INTO rules(id,label,severity,evidence_status,json) VALUES (?,?,?,?,?)",
            (
                r.get("id"),
                r.get("label"),
                r.get("severity"),
                r.get("evidence_status", EvidenceStatus.manual_seed_unverified.value),
                json.dumps(r, ensure_ascii=False),
            ),
        )
    for a in payload.get("actions", []):
        cur.execute(
            "INSERT INTO actions(id,label,action_type,json) VALUES (?,?,?,?)",
            (a.get("id"), a.get("label"), a.get("action_type"), json.dumps(a, ensure_ascii=False)),
        )
    for c in payload.get("conditions", []):
        cur.execute(
            "INSERT INTO conditions(id,label,json) VALUES (?,?,?)",
            (c.get("id"), c.get("label"), json.dumps(c, ensure_ascii=False)),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_kb(
    input_kb: Path,
    output_kb: Path,
    sqlite_path: Path,
    extracted_dir: Path | None = None,
) -> None:
    payload = json.loads(input_kb.read_text(encoding="utf-8"))

    if extracted_dir is not None and extracted_dir.is_dir():
        extracted = _load_extracted_dir(extracted_dir)
        payload = _merge_payloads(payload, extracted)

    payload["concepts"] = _dedupe_by_id(payload.get("concepts", []))
    payload["rules"] = _dedupe_by_id(payload.get("rules", []))
    payload["actions"] = _dedupe_by_id(payload.get("actions", []))
    payload["conditions"] = _dedupe_by_id(payload.get("conditions", []))

    output_kb.parent.mkdir(parents=True, exist_ok=True)
    output_kb.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    _write_sqlite(payload, sqlite_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize/merge KB JSON and write SQLite snapshot.")
    parser.add_argument("--input", type=Path, default=Path("data/kb/kb.json"))
    parser.add_argument("--output", type=Path, default=Path("data/kb/kb.json"))
    parser.add_argument("--sqlite", type=Path, default=Path("data/kb/kb.sqlite"))
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        default=None,
        help="Directory with per-chunk extracted JSON files to merge into the KB.",
    )
    args = parser.parse_args()

    normalize_kb(args.input, args.output, args.sqlite, extracted_dir=args.extracted_dir)
    print(f"Normalized KB written to {args.output} and {args.sqlite}")


if __name__ == "__main__":
    main()

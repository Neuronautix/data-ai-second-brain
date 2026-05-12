from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _dedupe_by_id(items: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in items:
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id not in seen:
            seen[item_id] = item
        else:
            merged = seen[item_id]
            for key, value in item.items():
                if isinstance(value, list):
                    merged[key] = list(dict.fromkeys((merged.get(key, []) or []) + value))
    return list(seen.values())


def normalize_kb(input_kb: Path, output_kb: Path, sqlite_path: Path) -> None:
    payload = json.loads(input_kb.read_text(encoding="utf-8"))

    payload["concepts"] = _dedupe_by_id(payload.get("concepts", []))
    payload["rules"] = _dedupe_by_id(payload.get("rules", []))
    payload["actions"] = _dedupe_by_id(payload.get("actions", []))
    payload["conditions"] = _dedupe_by_id(payload.get("conditions", []))

    output_kb.parent.mkdir(parents=True, exist_ok=True)
    output_kb.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

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
        CREATE TABLE rules (id TEXT PRIMARY KEY, label TEXT, severity TEXT, json TEXT NOT NULL);
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
            "INSERT INTO rules(id,label,severity,json) VALUES (?,?,?,?)",
            (r.get("id"), r.get("label"), r.get("severity"), json.dumps(r, ensure_ascii=False)),
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize/merge KB JSON and write SQLite snapshot.")
    parser.add_argument("--input", type=Path, default=Path("data/kb/kb.json"))
    parser.add_argument("--output", type=Path, default=Path("data/kb/kb.json"))
    parser.add_argument("--sqlite", type=Path, default=Path("data/kb/kb.sqlite"))
    args = parser.parse_args()

    normalize_kb(args.input, args.output, args.sqlite)
    print(f"Normalized KB written to {args.output} and {args.sqlite}")


if __name__ == "__main__":
    main()

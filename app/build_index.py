from __future__ import annotations

"""
TODO (Phase 6+): Build vector / full-text index from normalized KB and chunks.

This module should be implemented AFTER extraction quality is acceptable.

Planned behaviour:
- Read all markdown chunks from data/chunks/chunks.jsonl
- Read normalized rules, concepts, and actions from data/kb/kb.json
- Build a searchable index (e.g. LanceDB, Chroma, or SQLite FTS5)
- Store source_id / chunk_id provenance in index metadata so every
  search hit can be traced back to the original source document
- Expose a simple query interface used by app/query_decision.py

Do NOT implement this before extraction produces validated JSON output
in data/extracted/ with acceptable recall and precision.
"""


def main() -> None:
    print("TODO: build optional vector / full-text index (Phase 6+).")


if __name__ == "__main__":
    main()

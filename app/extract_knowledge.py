from __future__ import annotations

"""
LLM-based structured knowledge extraction from document chunks.

Usage:
    python -m app.extract_knowledge \\
        --chunks data/chunks/chunks.jsonl \\
        --output-dir data/extracted \\
        --model gpt-4.1-mini \\
        --limit 10

Options:
    --dry-run       Print prompts without calling the LLM.
    --overwrite     Re-process chunks whose output file already exists.
    --limit N       Process only the first N chunks.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.schemas import EvidenceStatus, ExtractionResult


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_rules.md"


def _load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_prompt(template: str, chunk: dict) -> str:
    return (
        template
        .replace("<<source_id>>", chunk.get("source_id", "unknown"))
        .replace("<<chunk_id>>", chunk.get("chunk_id", "unknown"))
        .replace("<<section_title>>", chunk.get("section_title") or "N/A")
        .replace("<<chunk_text>>", chunk.get("text", ""))
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(prompt: str, model: str, client) -> str:  # type: ignore[type-arg]
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a governance knowledge extraction assistant. "
                    "Return ONLY valid JSON. No markdown fences. No prose."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict:
    """Strip optional markdown fences then parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last fence lines
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    return json.loads(text)


def _filter_rejected(payload_dict: dict) -> dict:
    """Remove rules with evidence_status=rejected before validation."""
    rules = payload_dict.get("rules", [])
    payload_dict["rules"] = [
        r for r in rules
        if r.get("evidence_status") != EvidenceStatus.rejected.value
    ]
    return payload_dict


def _validate_extraction(raw_dict: dict) -> ExtractionResult:
    filtered = _filter_rejected(raw_dict)
    return ExtractionResult.model_validate(filtered)


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

def extract_chunks(
    chunks_path: Path,
    output_dir: Path,
    model: str,
    limit: int | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    # Validate API key early
    if not dry_run:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print(
                "ERROR: OPENAI_API_KEY environment variable is not set.\n"
                "Set it with:  export OPENAI_API_KEY=sk-...\n"
                "Or use --dry-run to test prompts without calling the API.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            from openai import OpenAI
        except ImportError:
            print(
                "ERROR: openai package is not installed.\n"
                "Install it with:  pip install openai",
                file=sys.stderr,
            )
            sys.exit(1)
        client = OpenAI(api_key=api_key)
    else:
        client = None

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "extraction_log.jsonl"

    template = _load_prompt_template()

    chunks: list[dict] = []
    with open(chunks_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    if limit is not None:
        chunks = chunks[:limit]

    print(f"Processing {len(chunks)} chunk(s) → {output_dir}")

    with open(log_path, "a", encoding="utf-8") as log_fh:
        for chunk in chunks:
            chunk_id: str = chunk.get("chunk_id", "unknown")
            out_file = output_dir / f"{chunk_id}.json"

            if out_file.exists() and not overwrite:
                _log(log_fh, chunk_id, "skipped", note="output already exists")
                print(f"  SKIP  {chunk_id} (use --overwrite to reprocess)")
                continue

            prompt = _build_prompt(template, chunk)

            if dry_run:
                print(f"\n{'=' * 60}")
                print(f"DRY-RUN prompt for chunk: {chunk_id}")
                print("=" * 60)
                print(prompt)
                _log(log_fh, chunk_id, "dry_run")
                continue

            # Call LLM
            try:
                raw = _call_llm(prompt, model, client)
            except Exception as exc:
                _log(log_fh, chunk_id, "error", error=f"LLM call failed: {exc}")
                print(f"  ERROR {chunk_id}: LLM call failed — {exc}")
                continue

            # Parse JSON
            try:
                raw_dict = _parse_json(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                _log(log_fh, chunk_id, "error", error=f"JSON parse failed: {exc}", raw=raw[:500])
                print(f"  ERROR {chunk_id}: JSON parse failed — {exc}")
                continue

            # Validate with Pydantic
            try:
                result = _validate_extraction(raw_dict)
            except ValidationError as exc:
                _log(log_fh, chunk_id, "error", error=f"Validation failed: {exc}", raw=raw[:500])
                print(f"  ERROR {chunk_id}: Validation failed — {exc}")
                continue

            # Write output
            out_file.write_text(
                result.model_dump_json(indent=2, exclude_none=True),
                encoding="utf-8",
            )
            n_rules = len(result.rules)
            n_concepts = len(result.concepts)
            _log(log_fh, chunk_id, "success", rules=n_rules, concepts=n_concepts)
            print(f"  OK    {chunk_id}: {n_rules} rule(s), {n_concepts} concept(s)")

    print(f"\nLog written to {log_path}")


def _log(fh, chunk_id: str, status: str, **kwargs) -> None:  # type: ignore[type-arg]
    entry = {
        "chunk_id": chunk_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    fh.flush()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured governance knowledge from document chunks using an LLM."
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("data/chunks/chunks.jsonl"),
        help="Path to the input JSONL file with document chunks.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/extracted"),
        help="Directory to write extracted JSON files and the log.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI-compatible model name (default: gpt-4.1-mini).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N chunks (for testing).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompts without calling the LLM.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-process chunks whose output file already exists.",
    )
    args = parser.parse_args()

    extract_chunks(
        chunks_path=args.chunks,
        output_dir=args.output_dir,
        model=args.model,
        limit=args.limit,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()

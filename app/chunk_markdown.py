from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.schemas import DocumentChunk


def _split_sections(text: str) -> list[tuple[str | None, int, int]]:
    lines = text.splitlines(keepends=True)
    sections: list[tuple[str | None, int, int]] = []
    current_title: str | None = None
    start = 0
    cursor = 0

    for line in lines:
        is_heading = line.lstrip().startswith("#")
        if is_heading and cursor > start:
            sections.append((current_title, start, cursor))
            start = cursor
            current_title = line.strip("# \n") or None
        elif is_heading and cursor == 0:
            current_title = line.strip("# \n") or None
        cursor += len(line)

    if cursor > start:
        sections.append((current_title, start, cursor))
    return sections


def _chunk_text(source_id: str, text: str, chunk_chars: int, overlap_chars: int) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    sections = _split_sections(text)
    i = 0

    for section_title, section_start, section_end in sections:
        pos = section_start
        while pos < section_end:
            end = min(pos + chunk_chars, section_end)
            snippet = text[pos:end].strip()
            if snippet:
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{source_id}:chunk:{i}",
                        source_id=source_id,
                        section_title=section_title,
                        text=snippet,
                        char_start=pos,
                        char_end=end,
                    )
                )
                i += 1
            if end >= section_end:
                break
            pos = max(section_start, end - overlap_chars)

    return chunks


def chunk_markdown_dir(input_dir: Path, output_jsonl: Path, chunk_chars: int, overlap_chars: int) -> int:
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with output_jsonl.open("w", encoding="utf-8") as out:
        for md_file in sorted(input_dir.glob("*.md")):
            source_id = md_file.stem
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            chunks = _chunk_text(source_id, text, chunk_chars=chunk_chars, overlap_chars=overlap_chars)
            for chunk in chunks:
                out.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) + "\n")
            total += len(chunks)

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk markdown files into JSONL chunks.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/markdown"))
    parser.add_argument("--output", type=Path, default=Path("data/chunks/chunks.jsonl"))
    parser.add_argument("--chunk-chars", type=int, default=7000)
    parser.add_argument("--overlap-chars", type=int, default=900)
    args = parser.parse_args()

    total = chunk_markdown_dir(args.input_dir, args.output, args.chunk_chars, args.overlap_chars)
    print(f"Wrote {total} chunks.")


if __name__ == "__main__":
    main()

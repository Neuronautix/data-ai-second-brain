from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path

from app.schemas import DocumentSource


def _source_id(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"src.{path.stem}.{digest}"


def _convert_with_docling(path: Path) -> str:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise RuntimeError(
            "Docling is not installed. Install optional dependency: pip install .[ingestion]"
        ) from exc

    converter = DocumentConverter()
    result = converter.convert(str(path))
    return result.document.export_to_markdown()


def _to_markdown(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    return _convert_with_docling(path)


def ingest_documents(
    input_dir: Path,
    output_markdown_dir: Path,
    output_provenance_jsonl: Path,
    authority: str,
    trust_level: str,
) -> list[DocumentSource]:
    output_markdown_dir.mkdir(parents=True, exist_ok=True)
    output_provenance_jsonl.parent.mkdir(parents=True, exist_ok=True)

    sources: list[DocumentSource] = []
    supported_suffixes = {".pdf", ".docx", ".doc", ".txt", ".md"}
    for path in sorted(input_dir.glob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in supported_suffixes:
            continue

        markdown = _to_markdown(path)
        sid = _source_id(path)
        md_path = output_markdown_dir / f"{sid}.md"
        md_path.write_text(markdown, encoding="utf-8")

        source = DocumentSource(
            source_id=sid,
            title=path.stem,
            source_type="document",
            authority=authority,
            url_or_path=str(path.resolve()),
            date_ingested=datetime.now(UTC),
            trust_level=trust_level,
        )
        sources.append(source)

        with output_provenance_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(source.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDF/DOCX/TXT/MD into Markdown.")
    parser.add_argument("--input-dir", type=Path, default=Path("sources/pdf"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/markdown"))
    parser.add_argument("--provenance", type=Path, default=Path("data/kb/provenance.jsonl"))
    parser.add_argument("--authority", default="institutional")
    parser.add_argument("--trust-level", default="trusted")
    args = parser.parse_args()

    sources = ingest_documents(
        input_dir=args.input_dir,
        output_markdown_dir=args.output_dir,
        output_provenance_jsonl=args.provenance,
        authority=args.authority,
        trust_level=args.trust_level,
    )
    print(f"Ingested {len(sources)} document(s).")


if __name__ == "__main__":
    main()

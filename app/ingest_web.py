from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path
from urllib.request import urlopen

import yaml

from app.schemas import DocumentSource, SeedURL


def _source_id(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"web.{digest}"


def _extract_markdown(url: str) -> str:
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded, include_links=True, output_format="markdown")
        if text:
            return text
    except Exception:
        pass

    with urlopen(url, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return raw


def ingest_urls(seed_file: Path, output_dir: Path, provenance_path: Path) -> list[DocumentSource]:
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)

    loaded = yaml.safe_load(seed_file.read_text(encoding="utf-8")) or {}
    entries = loaded.get("urls", [])

    sources: list[DocumentSource] = []
    for raw_entry in entries:
        entry = SeedURL.model_validate(raw_entry)
        sid = _source_id(entry.url)
        markdown = _extract_markdown(entry.url)

        (output_dir / f"{sid}.md").write_text(markdown, encoding="utf-8")

        source = DocumentSource(
            source_id=sid,
            title=entry.title or entry.url,
            source_type="web",
            authority=entry.authority,
            url_or_path=entry.url,
            date_ingested=datetime.now(UTC),
            trust_level=entry.trust_level,
        )
        sources.append(source)

        with provenance_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(source.model_dump(mode="json"), ensure_ascii=False) + "\n")

    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest seed URLs into Markdown.")
    parser.add_argument("--seed-file", type=Path, default=Path("sources/urls/seed_urls.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/markdown"))
    parser.add_argument("--provenance", type=Path, default=Path("data/kb/provenance.jsonl"))
    args = parser.parse_args()

    sources = ingest_urls(args.seed_file, args.output_dir, args.provenance)
    print(f"Ingested {len(sources)} URL(s).")


if __name__ == "__main__":
    main()

# data-ai-second-brain

Lightweight and extensible **healthcare data/AI governance second brain** for CHU / university hospital contexts.

## MVP objective

Evidence-grounded decision support pipeline:

**Documents/URLs → Markdown → chunks → structured extraction → normalized KB → project triage assistant**

This assistant does **not** approve projects and does **not** provide legal advice. It supports framing and requires DPO/legal validation.

## Repository structure

```text
.
├── app/
├── prompts/
├── sources/
│   ├── pdf/
│   ├── urls/
│   └── notes/
├── data/
│   ├── raw/
│   ├── markdown/
│   ├── chunks/
│   ├── extracted/
│   ├── kb/
│   └── indexes/
└── tests/
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
# optional for ingestion and UI:
# pip install -e .[ingestion,ui]
```

## Phase-1/2 usage (implemented)

### 1) Ingest documents (Docling-backed when available)

```bash
python -m app.ingest_pdf --input-dir sources/pdf
```

### 2) Ingest seed URLs (Trafilatura-backed when available)

```bash
python -m app.ingest_web --seed-file sources/urls/seed_urls.yaml
```

### 3) Chunk markdown

```bash
python -m app.chunk_markdown --input-dir data/markdown --output data/chunks/chunks.jsonl
```

### 4) Normalize seeded KB to JSON + SQLite

```bash
python -m app.normalize_kb --input data/kb/kb.json --output data/kb/kb.json --sqlite data/kb/kb.sqlite
```

### 5) Run project triage

```bash
python -m app.query_decision "AI project using patient data with private partner and export request"
```

### 6) Optional Streamlit UI

```bash
streamlit run app/ui_streamlit.py
```

## Current implementation status

- ✅ Folder skeleton and seeded KB
- ✅ Pydantic schemas with "no evidence, no rule"
- ✅ Basic document and URL ingestion
- ✅ Markdown chunking
- ✅ Minimal decision assistant and DPO/legal brief tab
- ✅ LLM-based extraction (`app/extract_knowledge.py`)
- ✅ KB normalization with deduplication (`app/normalize_kb.py`)
- ✅ Evidence consistency validation and rejected-rule logging
- ✅ Extraction quality review (`app/review_extractions.py`)
- ✅ KB inspection (`app/inspect_kb.py`)
- ⚠️ TODO: Vector index building (`app/build_index.py`)

## Phase 4 / 4.5 workflow

### Extract knowledge from chunks

```bash
python -m app.extract_knowledge \
    --chunks data/chunks/chunks.jsonl \
    --output-dir data/extracted \
    --limit 10
```

### Review extraction quality

```bash
python -m app.review_extractions --extracted-dir data/extracted
# Filter by domain or status:
python -m app.review_extractions --extracted-dir data/extracted --domain RGPD --show-rules
python -m app.review_extractions --extracted-dir data/extracted --status source_supported
```

### Merge extractions into the KB

```bash
python -m app.normalize_kb \
    --input data/kb/kb.json \
    --extracted-dir data/extracted \
    --output data/kb/kb.json \
    --sqlite data/kb/kb.sqlite
```

### Inspect the normalized KB

```bash
python -m app.inspect_kb --kb data/kb/kb.json
```

The `review_extractions` command summarizes extraction quality (status breakdown, top domains,
duplicate labels, rules missing source evidence, rejected candidates).

The `inspect_kb` command identifies weak rules (missing actions/conditions), manual/unverified
rules, high-severity rules, duplicate IDs, and evidence coverage.

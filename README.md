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
- ⚠️ TODO: LLM-based extraction (`app/extract_knowledge.py`)
- ⚠️ TODO: Vector index building (`app/build_index.py`)

## Testing

```bash
pytest
```

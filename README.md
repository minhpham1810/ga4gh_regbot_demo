# GA4GH RegBot — MVP Prototype

A local-first, RAG-powered compliance assistant for genomic data sharing.

Upload a data use letter (DUL), consent form, or related document and receive a
citation-grounded compliance gap analysis against the GA4GH policy corpus.

> **Note:** This is an MVP prototype for research/demonstration purposes.
> Sample corpus files are included as seed data — they are synthetic approximations
> of GA4GH documents, not official publications.

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running locally
- A supported model pulled: `ollama pull mistral:7b-instruct`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment (optional)

```bash
cp .env.example .env
# Edit .env to change model, paths, etc.
```

### 4. Run the app

```bash
streamlit run ui/app.py
```

### 5. Ingest the corpus

Click **"Ingest sample corpus"** in the sidebar. This embeds the sample GA4GH
documents into ChromaDB. Only needs to be done once (persisted to `chroma_db/`).

To ingest your own documents, add PDFs or TXT files to `data/ga4gh_corpus/` and
click Ingest again (or run `python -m ingestion.ingest`).

---

## Architecture

```
Upload document
      │
      ▼
classify_domains()          ← keyword-based domain tagger
      │
      ▼
retrieve()                  ← ChromaDB semantic search
      │                        (sentence-transformers/all-MiniLM-L6-v2)
      ▼
detect_gaps()               ← Ollama LLM (mistral:7b-instruct)
      │                        KNOWLEDGE BLOCK = retrieved chunks
      ▼
validate_verdicts()         ← cross-checks every anchor_id
      │                        against the retrieved set
      ▼
Streamlit chat UI           ← chat-first, with expandable evidence
```

---

## Project Structure

```
ga4gh-regbot/
├── ingestion/
│   ├── ingest.py          # Orchestration: load → chunk → embed → persist
│   ├── chunker.py         # Page-aware chunking
│   ├── metadata.py        # ChunkMetadata Pydantic schema
│   ├── loaders.py         # PDF/TXT loaders (PyMuPDF)
│   └── anchors.py         # Anchor extraction (DUO > numbered > heading > page)
├── retrieval/
│   ├── retriever.py       # ChromaDB semantic retrieval
│   ├── classifier.py      # Keyword-based domain classifier
│   └── decomposer.py      # TODO: sub-query decomposition (stub)
├── generation/
│   ├── pipeline.py        # End-to-end analysis pipeline
│   ├── gap_detector.py    # LLM prompting via Ollama
│   ├── validator.py       # Citation anchor validation
│   └── prompts/
│       ├── system.md      # System prompt (evidence-only enforcement)
│       └── __init__.py
├── ui/
│   ├── app.py             # Chat-first Streamlit app
│   └── pdf_viewer.py      # In-app PDF viewer
├── evaluation/
│   ├── test_retrieval.py  # Ingestion + retrieval tests
│   └── test_citations.py  # Citation validator tests
├── data/
│   ├── ga4gh_corpus/      # GA4GH policy documents (add your PDFs here)
│   │   └── cache/         # Auto-populated during ingestion
│   └── test_duls/         # Sample researcher documents
├── chroma_db/             # Persistent ChromaDB (auto-created)
├── config.py
├── requirements.txt
└── .env.example
```

---

## Anchor Metadata Design

Each ingested chunk is tagged with:

| Field | Description |
|-------|-------------|
| `anchor_id` | Canonical citation anchor (`DUO:0000007`, `4.3`, `data-sharing`, `1`) |
| `anchor_type` | `duo_term` / `numbered_section` / `section_heading` / `page_only` |
| `section_title` | Human-readable heading |
| `doc_type` | `framework` / `guideline` / `template_clause_bank` / etc. |
| `page` | 1-indexed source page |
| `title` | Source document title |
| `source_url` | Original URL (Google Drive or other) |
| `drive_file_id` | Google Drive file ID (for cache lookup) |

Anchor extraction priority: **DUO term → numbered clause → heading → page fallback**

---

## Running Tests

```bash
pytest evaluation/ -v
```

Tests use an isolated ChromaDB tmp directory — safe to run in CI.

---

## Configuring for Real GA4GH Documents

1. Download GA4GH PDFs from Google Drive into `data/ga4gh_corpus/`
2. Optionally annotate filenames to hint at doc_type:
   - `framework_*` → `framework`
   - `duo_*` or `machine_readable_*` → `guideline`
   - `clause_bank_*` or `template_*` → `template_clause_bank`
3. Run `python -m ingestion.ingest` or click **Ingest** in the sidebar
4. Set `LLM_MODEL` in `.env` to your preferred Ollama model

---

## Limitations (MVP)

- No OCR for scanned/image PDFs (text-layer PDFs only)
- No ontology graph traversal
- Single-user, local only
- No hybrid BM25+dense retrieval (dense only)
- No reranker
- Streamlit session state is ephemeral (resets on page reload)

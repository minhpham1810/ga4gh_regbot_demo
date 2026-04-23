# GA4GH-RegBot Demo

GA4GH-RegBot is a local-first RAG prototype for reviewing genomic data-sharing language against a small GA4GH standards corpus. The repository is intentionally scoped as an MVP demo: it supports corpus Q&A, uploaded-document review, source-aware retrieval, and citation validation, but it does not claim production readiness.

## What this demo does

- Runs a Streamlit chat UI for:
  - grounded corpus Q&A over GA4GH sources
  - uploaded document review against retrieved obligations
  - in-app source preview for cached PDF / OWL artifacts
- Parses a curated GA4GH corpus from `data/manifest.yaml`
- Retrieves metadata-aware chunks with `article_id`, `article_scheme`, `source_id`, and page provenance
- Validates cited article IDs against the retrieved set and downgrades unsupported citations to `unverified`

## Why this is different from a general chatbot

This project is built around a narrow trust boundary:

- retrieval is limited to a curated GA4GH corpus
- answers are expected to cite clause or ontology-level `article_id` values
- the validator explicitly checks that cited article IDs came from retrieval

The goal is not open-ended chatting. The goal is an inspectable compliance assistant with grounded outputs.

## Current MVP scope

Included now:

- manifest-driven corpus definitions
- PDF and OWL parsing for the current demo corpus
- source-aware chunking and metadata
- local Chroma retrieval client
- single-turn / follow-up chat flow in Streamlit
- document review with structured verdicts
- citation validation for verdicts and inline corpus-answer citations

Intentionally not implemented yet:

- OCR for scanned PDFs
- hybrid retrieval or reranking
- multi-hop reasoning across many sources
- collaborative workflows or user accounts
- production deployment, monitoring, or hardening
- complete Chroma write-back in `ingestion/ingest.py` (the parser pipeline exists; persistence is not yet implemented)

## Repository structure

```text
.
|-- README.md
|-- requirements.txt
|-- .env.example
|-- config.py
|-- ingestion/
|   |-- ingest.py
|   |-- loaders.py
|   |-- chunker.py
|   |-- manifest.py
|   |-- metadata.py
|   `-- parsers.py
|-- retrieval/
|   |-- classifier.py
|   `-- retriever.py
|-- generation/
|   |-- pipeline.py
|   |-- gap_detector.py
|   |-- validator.py
|   |-- router.py
|   `-- prompts/
|-- ui/
|   |-- app.py
|   `-- pdf_viewer.py
|-- data/
|   |-- manifest.yaml
|   |-- raw/
|   `-- samples/
|-- tests/
|   |-- test_retrieval.py
|   `-- test_validator.py
`-- docs/
    |-- architecture.md
    |-- demo-example.md
    `-- archive/
```

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure local environment

Copy `.env.example` to `.env` and adjust values if needed.

The default setup assumes:

- Ollama is running locally at `http://localhost:11434`
- a local embedding model can be loaded for Chroma retrieval

### 3. Optional: fetch and parse the source corpus

```bash
python -m ingestion.ingest
```

This command fetches raw source artifacts and parses them into chunked `Document` objects. At the moment it does **not** persist those chunks back into Chroma automatically; that persistence step is not yet implemented in this repo.

### 4. Run the app

```bash
streamlit run ui/app.py
```

If a local Chroma collection is already populated, you can:

- ask a GA4GH / DUO question in chat
- upload `data/samples/sample_dul.txt`
- ask for a review such as `What are the biggest gaps?`

If the vector store is empty, the app still runs, but grounded retrieval features will tell you that no relevant corpus passages were found.

## Demo example

A reproducible sample review input is provided at `data/samples/sample_dul.txt`.

Expected demo flow:

1. Start the app with `streamlit run ui/app.py`
2. Attach `data/samples/sample_dul.txt`
3. Ask `What are the biggest gaps?`
4. Inspect verdicts, narrative summary, and any grounded source previews

See `docs/demo-example.md` for an example walkthrough.

## Trust and limitations

This repository should be read as an honest MVP, not a finished product.

- Citation validation is implemented and is one of the main trust mechanisms in the demo.
- Retrieval is local and inspectable, but still basic.
- The corpus ingestion path is real, but Chroma persistence is incomplete.
- Source previews depend on cached files in `data/raw/`.
- The UI is optimized for demo clarity, not production polish.

## Project direction

The next sensible steps are:

- wire parsed chunks into Chroma persistence
- improve retrieval quality with reranking / hybrid search
- expand test coverage beyond the current minimal checks
- tighten the document-review prompt and evidence presentation
- harden the app around failure cases and corpus refresh flows

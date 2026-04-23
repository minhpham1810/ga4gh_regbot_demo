# Architecture

GA4GH-RegBot is a local-first prototype for grounded compliance assistance over a small GA4GH policy corpus. The repository is intentionally narrow: one Streamlit demo path, one retrieval path, one generation path, and one citation-validation step.

## MVP flow

1. `ui/app.py`
   - Chat-first Streamlit interface
   - Supports plain conversational turns, corpus Q&A, and uploaded document review
   - Opens cached source previews for cited evidence
2. `generation/pipeline.py`
   - Routes each turn through the single MVP pipeline
   - Chooses between plain chat, corpus Q&A, and document review
   - Only shows grounded sources when article IDs are actually cited
3. `retrieval/retriever.py`
   - Reads chunk metadata from a local Chroma collection
   - Returns source-aware chunks with `article_id`, `article_scheme`, `source_id`, and page provenance
4. `generation/gap_detector.py`
   - Builds the LLM context from retrieved chunks
   - Produces either a direct corpus answer or a structured document-review response
5. `generation/validator.py`
   - Validates cited `article_id` values against the retrieved set
   - Marks unsupported citations as `unverified`
6. `ingestion/`
   - Loads a manifest of corpus sources
   - Fetches and caches raw PDF / OWL artifacts
   - Parses page-level PDFs and DUO ontology terms
   - Chunks documents with source-aware article extraction

## Data layout

- `data/manifest.yaml`
  The curated list of GA4GH sources used by the demo
- `data/raw/`
  Runtime cache for fetched PDFs and OWL files
- `data/samples/`
  Small demo inputs for local review runs

## Retrieval and trust model

The demo is not a general chatbot. It uses retrieval and source metadata to constrain what the model can cite.

- Corpus Q&A is grounded in retrieved chunks
- Document review compares uploaded text against retrieved obligations
- Citation validation only trusts article IDs that appeared in retrieval

This does not make the system production-ready, but it gives the MVP a concrete trust boundary: cited article IDs must be traceable to retrieved source material.

## Honest gaps

- `ingestion/ingest.py` still stops at parsed/chunked `Document` objects; Chroma persistence is not yet implemented
- No OCR pipeline is implemented
- No reranking or hybrid retrieval is implemented
- No multi-hop reasoning or multi-document workspace is implemented
- The UI is deliberately minimal and local-first

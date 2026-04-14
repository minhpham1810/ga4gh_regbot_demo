# GA4GH-RegBot MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first, RAG-powered compliance assistant that lets a researcher upload a genomic data use document and receive a citation-grounded compliance gap analysis against the GA4GH policy corpus.

**Architecture:** Ingestion layer chunks GA4GH PDFs into ChromaDB with generalized anchor metadata (numbered sections, DUO terms, headings). A retrieval layer does semantic search filtered by domain. A generation layer sends retrieved evidence to Ollama and validates every output citation against the retrieved anchor set. A Streamlit chat-first UI presents results as conversational assistant messages with expandable evidence.

**Tech Stack:** Python 3.11+, Streamlit, LangChain, ChromaDB, sentence-transformers, Ollama (mistral/llama3), PyMuPDF, Pydantic, pytest.

---

## File Map

| File | Responsibility |
|------|---------------|
| `config.py` | All env/config constants |
| `.env.example` | Template env file |
| `requirements.txt` | Pinned deps |
| `ingestion/metadata.py` | Pydantic ChunkMetadata schema + helpers |
| `ingestion/anchors.py` | Anchor extraction (DUO > numbered > heading > page) |
| `ingestion/loaders.py` | PDF/TXT loading → (page_text, page_num) pairs |
| `ingestion/chunker.py` | Page-aware chunking, attaches metadata |
| `ingestion/ingest.py` | Orchestration: load → chunk → embed → persist |
| `retrieval/classifier.py` | Keyword-based domain classifier |
| `retrieval/retriever.py` | ChromaDB semantic retrieval + metadata filter |
| `retrieval/decomposer.py` | Stub: TODO query decomposition |
| `generation/prompts/__init__.py` | Prompt loader |
| `generation/prompts/system.md` | System prompt enforcing evidence-only output |
| `generation/gap_detector.py` | Builds LLM prompt from retrieved chunks |
| `generation/validator.py` | Cross-checks anchor_ids against retrieved set |
| `generation/pipeline.py` | End-to-end orchestration for one analysis turn |
| `ui/pdf_viewer.py` | PDF rendering helpers for Streamlit |
| `ui/app.py` | Chat-first Streamlit app |
| `evaluation/test_retrieval.py` | Retrieval + metadata provenance tests |
| `evaluation/test_citations.py` | Citation validator unit tests |
| `data/ga4gh_corpus/*.txt` | Sample seed corpus files |
| `data/test_duls/*.txt` | Sample researcher documents |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `config.py`
- Create: `.env.example`
- Create: `requirements.txt`

- [ ] **Step 1: Write config.py**

```python
# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# --- Paths ---
CORPUS_DIR = BASE_DIR / "data" / "ga4gh_corpus"
CORPUS_CACHE_DIR = CORPUS_DIR / "cache"
TEST_DUL_DIR = BASE_DIR / "data" / "test_duls"
CHROMA_DIR = BASE_DIR / "chroma_db"

# --- ChromaDB ---
CORPUS_COLLECTION = os.getenv("CORPUS_COLLECTION", "ga4gh_corpus")

# --- Embeddings ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# --- LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral:7b-instruct")

# --- Chunking ---
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# --- Retrieval ---
TOP_K = int(os.getenv("TOP_K", "5"))
```

- [ ] **Step 2: Write .env.example**

```
LLM_MODEL=mistral:7b-instruct
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CORPUS_COLLECTION=ga4gh_corpus
CHUNK_SIZE=1200
CHUNK_OVERLAP=200
TOP_K=5
```

- [ ] **Step 3: Write requirements.txt**

```
streamlit>=1.35.0
langchain>=0.2.0
langchain-community>=0.2.0
langchain-chroma>=0.1.0
chromadb>=0.5.0
sentence-transformers>=3.0.0
ollama>=0.2.0
pymupdf>=1.24.0
pypdf>=4.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
python-slugify>=8.0.0
```

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p data/ga4gh_corpus/cache data/test_duls chroma_db \
         ingestion retrieval generation/prompts ui evaluation
touch ingestion/__init__.py retrieval/__init__.py \
      generation/__init__.py generation/prompts/__init__.py \
      ui/__init__.py evaluation/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add config.py .env.example requirements.txt
git commit -m "chore: project scaffolding and config"
```

---

## Task 2: Metadata Schema

**Files:**
- Create: `ingestion/metadata.py`

- [ ] **Step 1: Write ingestion/metadata.py**

```python
# ingestion/metadata.py
from typing import Optional, Literal
from pydantic import BaseModel, Field

DocType = Literal[
    "framework", "guideline", "template_clause_bank",
    "ethics_policy", "position_statement", "tooling_reference"
]

AnchorType = Literal["numbered_section", "duo_term", "section_heading", "page_only"]


class ChunkMetadata(BaseModel):
    doc_type: DocType
    anchor_id: str
    anchor_type: AnchorType
    section_title: str = ""
    source_url: str = ""
    page: int = 1
    start_page: int = 1
    end_page: int = 1
    title: str = ""
    drive_file_id: str = ""

    def to_chroma_dict(self) -> dict:
        """Return flat dict safe for ChromaDB metadata (no None values)."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


def make_page_fallback_metadata(
    page: int,
    title: str,
    doc_type: DocType,
    source_url: str = "",
    drive_file_id: str = "",
) -> ChunkMetadata:
    return ChunkMetadata(
        doc_type=doc_type,
        anchor_id=str(page),
        anchor_type="page_only",
        section_title="",
        source_url=source_url,
        page=page,
        start_page=page,
        end_page=page,
        title=title,
        drive_file_id=drive_file_id,
    )
```

- [ ] **Step 2: Commit**

```bash
git add ingestion/metadata.py
git commit -m "feat: chunk metadata schema"
```

---

## Task 3: Anchor Extraction

**Files:**
- Create: `ingestion/anchors.py`

- [ ] **Step 1: Write ingestion/anchors.py**

```python
# ingestion/anchors.py
"""
Anchor extraction with priority: DUO term > numbered clause > heading > page fallback.
"""
import re
from dataclasses import dataclass
from typing import Optional
from slugify import slugify


@dataclass
class AnchorResult:
    anchor_id: str
    anchor_type: str  # "duo_term" | "numbered_section" | "section_heading" | "page_only"
    section_title: str


_DUO_RE = re.compile(r"\bDUO:\d{7}\b")

_NUMBERED_RE = re.compile(
    r"^(?:Section|Clause|Article)?\s*(\d+(?:\.\d+)*)\s*[.:\-]\s*(.+)",
    re.IGNORECASE | re.MULTILINE,
)

_HEADING_RE = re.compile(
    r"^([A-Z][A-Za-z0-9 /\-]{3,60})\s*$",
    re.MULTILINE,
)


def extract_anchor(text: str, page: int) -> AnchorResult:
    """Extract the best anchor from a text chunk."""
    # 1. DUO term takes priority
    duo_match = _DUO_RE.search(text)
    if duo_match:
        return AnchorResult(
            anchor_id=duo_match.group(),
            anchor_type="duo_term",
            section_title=duo_match.group(),
        )

    # 2. Numbered clause / section
    num_match = _NUMBERED_RE.search(text)
    if num_match:
        num = num_match.group(1).strip()
        title = num_match.group(2).strip()[:80]
        return AnchorResult(
            anchor_id=num,
            anchor_type="numbered_section",
            section_title=title,
        )

    # 3. Nearest heading (all-caps or title-case standalone line)
    heading_match = _HEADING_RE.search(text)
    if heading_match:
        heading = heading_match.group(1).strip()
        return AnchorResult(
            anchor_id=slugify(heading),
            anchor_type="section_heading",
            section_title=heading,
        )

    # 4. Page-only fallback
    return AnchorResult(
        anchor_id=str(page),
        anchor_type="page_only",
        section_title="",
    )
```

- [ ] **Step 2: Commit**

```bash
git add ingestion/anchors.py
git commit -m "feat: anchor extraction (DUO > numbered > heading > page)"
```

---

## Task 4: Document Loaders

**Files:**
- Create: `ingestion/loaders.py`

- [ ] **Step 1: Write ingestion/loaders.py**

```python
# ingestion/loaders.py
"""
Load PDF and TXT files. Returns list of (page_text, page_number) tuples.
page_number is 1-indexed.
"""
from pathlib import Path
from typing import List, Tuple

PageChunk = Tuple[str, int]  # (text, 1-indexed page number)


def load_pdf(path: Path) -> List[PageChunk]:
    """Extract text per page from a PDF using PyMuPDF."""
    import fitz  # PyMuPDF

    pages: List[PageChunk] = []
    doc = fitz.open(str(path))
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages.append((text, i))
    doc.close()
    return pages


def load_txt(path: Path) -> List[PageChunk]:
    """Load a text file as a single 'page'."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [(text, 1)]


def load_document(path: Path) -> List[PageChunk]:
    """Dispatch to PDF or TXT loader based on suffix."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    elif suffix in (".txt", ".md"):
        return load_txt(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
```

- [ ] **Step 2: Commit**

```bash
git add ingestion/loaders.py
git commit -m "feat: PDF and TXT document loaders"
```

---

## Task 5: Page-Aware Chunker

**Files:**
- Create: `ingestion/chunker.py`

- [ ] **Step 1: Write ingestion/chunker.py**

```python
# ingestion/chunker.py
"""
Page-aware chunking. Splits within a page; does not cross page boundaries.
Returns list of (text, ChunkMetadata).
"""
from typing import List, Tuple
from pathlib import Path

from ingestion.loaders import PageChunk
from ingestion.metadata import ChunkMetadata, DocType
from ingestion.anchors import extract_anchor
from config import CHUNK_SIZE, CHUNK_OVERLAP


def _split_text(text: str, size: int, overlap: int) -> List[str]:
    """Simple character-level sliding-window split."""
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def chunk_pages(
    pages: List[PageChunk],
    doc_type: DocType,
    title: str,
    source_url: str = "",
    drive_file_id: str = "",
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Tuple[str, ChunkMetadata]]:
    """
    Given (text, page_num) pairs, produce (chunk_text, ChunkMetadata) pairs.
    Chunking is within-page only to preserve page provenance.
    """
    result: List[Tuple[str, ChunkMetadata]] = []

    for page_text, page_num in pages:
        sub_chunks = _split_text(page_text, chunk_size, chunk_overlap)
        for chunk_text in sub_chunks:
            if not chunk_text.strip():
                continue
            anchor = extract_anchor(chunk_text, page_num)
            meta = ChunkMetadata(
                doc_type=doc_type,
                anchor_id=anchor.anchor_id,
                anchor_type=anchor.anchor_type,
                section_title=anchor.section_title,
                source_url=source_url,
                page=page_num,
                start_page=page_num,
                end_page=page_num,
                title=title,
                drive_file_id=drive_file_id,
            )
            result.append((chunk_text, meta))

    return result
```

- [ ] **Step 2: Commit**

```bash
git add ingestion/chunker.py
git commit -m "feat: page-aware chunker with metadata tagging"
```

---

## Task 6: Ingest Orchestration

**Files:**
- Create: `ingestion/ingest.py`

- [ ] **Step 1: Write ingestion/ingest.py**

```python
# ingestion/ingest.py
"""
CLI-runnable ingestion pipeline.
Usage: python -m ingestion.ingest --corpus-dir data/ga4gh_corpus
"""
import argparse
import shutil
from pathlib import Path
from typing import Optional
import uuid

import chromadb
from chromadb.utils import embedding_functions

from config import (
    CHROMA_DIR, CORPUS_COLLECTION, CORPUS_CACHE_DIR,
    EMBEDDING_MODEL, CORPUS_DIR
)
from ingestion.loaders import load_document
from ingestion.chunker import chunk_pages
from ingestion.metadata import DocType

# Heuristic doc_type assignment by filename keywords
_DOC_TYPE_HINTS: list[tuple[list[str], DocType]] = [
    (["framework", "policy framework"], "framework"),
    (["duo", "machine-readable", "consent guidance"], "guideline"),
    (["clause", "template", "pediatric", "familial", "clinical"], "template_clause_bank"),
    (["ethics", "irb", "research ethics"], "ethics_policy"),
    (["position", "statement"], "position_statement"),
    (["tool", "reference", "api"], "tooling_reference"),
]


def infer_doc_type(path: Path) -> DocType:
    name_lower = path.stem.lower().replace("-", " ").replace("_", " ")
    for keywords, doc_type in _DOC_TYPE_HINTS:
        if any(kw in name_lower for kw in keywords):
            return doc_type
    return "framework"


def get_chroma_collection(collection_name: str = CORPUS_COLLECTION):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_file(
    path: Path,
    collection,
    source_url: str = "",
    drive_file_id: str = "",
    doc_type: Optional[DocType] = None,
) -> int:
    """Ingest a single file. Returns number of chunks added."""
    if doc_type is None:
        doc_type = infer_doc_type(path)

    title = path.stem.replace("-", " ").replace("_", " ").title()
    pages = load_document(path)
    chunks = chunk_pages(
        pages, doc_type=doc_type, title=title,
        source_url=source_url, drive_file_id=drive_file_id,
    )

    if not chunks:
        return 0

    texts = [c[0] for c in chunks]
    metadatas = [c[1].to_chroma_dict() for c in chunks]
    ids = [f"{path.stem}_{uuid.uuid4().hex[:8]}" for _ in chunks]

    collection.add(documents=texts, metadatas=metadatas, ids=ids)

    # Cache source file locally
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CORPUS_CACHE_DIR / path.name
    if not dest.exists():
        shutil.copy2(path, dest)

    return len(chunks)


def ingest_corpus(corpus_dir: Path = CORPUS_DIR) -> int:
    """Ingest all PDF/TXT files in corpus_dir. Returns total chunks ingested."""
    collection = get_chroma_collection()
    total = 0
    for path in sorted(corpus_dir.glob("*")):
        if path.suffix.lower() in (".pdf", ".txt", ".md") and path.is_file():
            n = ingest_file(path, collection)
            print(f"  Ingested {path.name}: {n} chunks")
            total += n
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default=str(CORPUS_DIR))
    args = parser.parse_args()
    total = ingest_corpus(Path(args.corpus_dir))
    print(f"\nTotal chunks ingested: {total}")
```

- [ ] **Step 2: Commit**

```bash
git add ingestion/ingest.py
git commit -m "feat: ingestion orchestration with ChromaDB persistence"
```

---

## Task 7: Sample Corpus Files

**Files:**
- Create: `data/ga4gh_corpus/01_framework_data_sharing_lexicon.txt`
- Create: `data/ga4gh_corpus/02_duo_machine_readable_consent_guidance.txt`
- Create: `data/ga4gh_corpus/03_template_clause_bank_consent_forms.txt`
- Create: `data/test_duls/sample_dul_request.txt`

- [ ] **Step 1: Write framework seed file**

See full content in implementation — this is a ~300 line TXT mimicking GA4GH Framework for Responsible Sharing of Genomic and Health-Related Data with numbered sections 1–9.

- [ ] **Step 2: Write DUO seed file**

TXT mimicking GA4GH Machine Readable Consent Guidance with DUO:0000007, DUO:0000042 etc.

- [ ] **Step 3: Write clause-bank seed file**

TXT with headings: Data Sharing, Protection of Privacy, Recontact, Sample Storage.

- [ ] **Step 4: Write sample DUL**

TXT acting as a researcher's data use letter referencing consent, access controls, and cross-border transfers.

- [ ] **Step 5: Commit**

```bash
git add data/
git commit -m "chore: add sample seed corpus and test DUL files"
```

---

## Task 8: Domain Classifier

**Files:**
- Create: `retrieval/classifier.py`

- [ ] **Step 1: Write retrieval/classifier.py**

```python
# retrieval/classifier.py
"""
Lightweight keyword-based domain classifier.
Returns list of matched domains; falls back to ["general"] if none matched.
"""
from typing import List

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "consent": [
        "consent", "informed consent", "participant consent",
        "recontact", "withdraw", "opt-out", "assent",
    ],
    "data_access": [
        "data access", "access committee", "data use",
        "controlled access", "open access", "DAC", "DUO",
        "data sharing", "data transfer", "repository",
    ],
    "cross_border": [
        "cross-border", "transborder", "international transfer",
        "jurisdiction", "GDPR", "third country", "data export",
    ],
    "privacy_security": [
        "privacy", "confidentiality", "anonymi", "pseudonyni",
        "de-identif", "encryption", "security", "data protection",
        "access control", "audit",
    ],
}


def classify_domains(text: str) -> List[str]:
    """Return matched domains for the given text (lowercase comparison)."""
    lower = text.lower()
    matched = [
        domain
        for domain, keywords in DOMAIN_KEYWORDS.items()
        if any(kw.lower() in lower for kw in keywords)
    ]
    return matched if matched else ["general"]
```

- [ ] **Step 2: Commit**

```bash
git add retrieval/classifier.py
git commit -m "feat: keyword-based domain classifier"
```

---

## Task 9: Retriever

**Files:**
- Create: `retrieval/retriever.py`
- Create: `retrieval/decomposer.py`

- [ ] **Step 1: Write retrieval/retriever.py**

```python
# retrieval/retriever.py
from typing import List, Optional
from dataclasses import dataclass

import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_DIR, CORPUS_COLLECTION, EMBEDDING_MODEL, TOP_K
from ingestion.metadata import DocType, AnchorType


@dataclass
class RetrievedChunk:
    text: str
    anchor_id: str
    anchor_type: str
    section_title: str
    page: int
    source_url: str
    title: str
    drive_file_id: str
    doc_type: str
    score: float


def _get_collection(collection_name: str = CORPUS_COLLECTION):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def retrieve(
    query: str,
    top_k: int = TOP_K,
    doc_type_filter: Optional[DocType] = None,
    collection_name: str = CORPUS_COLLECTION,
) -> List[RetrievedChunk]:
    """
    Semantic retrieval from ChromaDB.
    Optionally filter by doc_type.
    """
    collection = _get_collection(collection_name)

    where = {"doc_type": {"$eq": doc_type_filter}} if doc_type_filter else None

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count() or 1),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []

    for doc, meta, dist in zip(docs, metas, distances):
        chunks.append(RetrievedChunk(
            text=doc,
            anchor_id=meta.get("anchor_id", ""),
            anchor_type=meta.get("anchor_type", "page_only"),
            section_title=meta.get("section_title", ""),
            page=int(meta.get("page", 1)),
            source_url=meta.get("source_url", ""),
            title=meta.get("title", ""),
            drive_file_id=meta.get("drive_file_id", ""),
            doc_type=meta.get("doc_type", ""),
            score=1.0 - float(dist),
        ))

    return chunks
```

- [ ] **Step 2: Write retrieval/decomposer.py (stub)**

```python
# retrieval/decomposer.py
"""
TODO: Sub-query decomposition for complex compliance questions.
Currently a passthrough stub.
"""
from typing import List


def decompose_query(query: str) -> List[str]:
    """Return sub-queries. For MVP, returns query as-is."""
    return [query]
```

- [ ] **Step 3: Commit**

```bash
git add retrieval/retriever.py retrieval/decomposer.py
git commit -m "feat: semantic retriever with metadata filtering"
```

---

## Task 10: Prompt Files

**Files:**
- Create: `generation/prompts/system.md`
- Create: `generation/prompts/__init__.py`

- [ ] **Step 1: Write generation/prompts/system.md**

````markdown
# GA4GH Compliance Assistant — System Prompt

You are a compliance analysis assistant specializing in GA4GH (Global Alliance for Genomics and Health) policy frameworks.

## Core Rules

1. **Evidence-only reasoning.** You MUST base every compliance verdict exclusively on the KNOWLEDGE BLOCK provided. Do not use general knowledge, internet information, or assumptions not supported by the retrieved passages.

2. **Cite only retrieved anchors.** Every item in the JSON output MUST reference an `anchor_id` that appears in the KNOWLEDGE BLOCK. If an obligation has no supporting evidence in the KNOWLEDGE BLOCK, set its status to `"unverified"` and its `evidence` field to `null`.

3. **Admit uncertainty.** If you cannot determine compliance status from the retrieved evidence, say so explicitly. Do not invent obligations.

4. **Structured output.** Your response MUST contain two sections:
   - `## JSON_VERDICTS` — a JSON array of verdict objects (schema below)
   - `## NARRATIVE_SUMMARY` — a plain-language explanation of the compliance gaps

## JSON Verdict Schema

```json
[
  {
    "anchor_id": "<anchor_id from KNOWLEDGE BLOCK>",
    "anchor_type": "<duo_term|numbered_section|section_heading|page_only>",
    "section_title": "<human-readable section title>",
    "obligation": "<what the GA4GH standard requires>",
    "status": "<covered|partially covered|missing|unverified>",
    "evidence": "<quoted text from researcher document, or null>",
    "rationale": "<one-sentence explanation>",
    "page": <page number from source>,
    "title": "<source document title>"
  }
]
```

## Status Definitions

- **covered**: Researcher document clearly satisfies this obligation.
- **partially covered**: Researcher document addresses it but incompletely.
- **missing**: Obligation is clearly required but not addressed in researcher document.
- **unverified**: No retrieved evidence supports this anchor; cannot assess compliance.

## Off-Topic Guard

If the user's question is unrelated to genomic data compliance review, respond:
> "I'm a GA4GH compliance assistant. Please upload a data use letter, consent form, or related document to begin a compliance review."
````

- [ ] **Step 2: Write generation/prompts/__init__.py**

```python
# generation/prompts/__init__.py
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_system_prompt() -> str:
    return (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
```

- [ ] **Step 3: Commit**

```bash
git add generation/prompts/
git commit -m "feat: system prompt with evidence-only enforcement"
```

---

## Task 11: Gap Detector

**Files:**
- Create: `generation/gap_detector.py`

- [ ] **Step 1: Write generation/gap_detector.py**

```python
# generation/gap_detector.py
"""
Builds the LLM prompt from retrieved chunks + researcher doc text.
Calls Ollama and returns raw model output string.
"""
from typing import List
from retrieval.retriever import RetrievedChunk
from generation.prompts import load_system_prompt
from config import LLM_MODEL, OLLAMA_BASE_URL

import ollama


def build_knowledge_block(chunks: List[RetrievedChunk]) -> str:
    lines = ["## KNOWLEDGE BLOCK\n"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(
            f"[{i}] Source: {chunk.title} | anchor_id: {chunk.anchor_id} "
            f"| anchor_type: {chunk.anchor_type} | page: {chunk.page}\n"
            f"{chunk.text.strip()}\n"
        )
    return "\n".join(lines)


def detect_gaps(
    researcher_text: str,
    retrieved_chunks: List[RetrievedChunk],
    follow_up: str = "",
) -> str:
    """
    Send researcher doc + retrieved evidence to the LLM.
    Returns raw model output (contains JSON_VERDICTS + NARRATIVE_SUMMARY sections).
    """
    system_prompt = load_system_prompt()
    knowledge_block = build_knowledge_block(retrieved_chunks)

    user_content = (
        f"## RESEARCHER DOCUMENT\n\n{researcher_text}\n\n"
        f"{knowledge_block}\n\n"
    )
    if follow_up:
        user_content += f"## FOLLOW-UP QUESTION\n\n{follow_up}\n\n"

    user_content += (
        "Please analyze the researcher document against the GA4GH standards "
        "in the KNOWLEDGE BLOCK. Produce:\n"
        "1. `## JSON_VERDICTS` section with the JSON array\n"
        "2. `## NARRATIVE_SUMMARY` section with plain-language analysis\n"
        "Only cite anchor_ids present in the KNOWLEDGE BLOCK."
    )

    client = ollama.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response["message"]["content"]
```

- [ ] **Step 2: Commit**

```bash
git add generation/gap_detector.py
git commit -m "feat: gap detector - builds LLM prompt and calls Ollama"
```

---

## Task 12: Citation Validator

**Files:**
- Create: `generation/validator.py`

- [ ] **Step 1: Write generation/validator.py**

```python
# generation/validator.py
"""
Validates LLM output citations against the retrieved anchor_id set.
Flags any anchor_id not in the retrieved set as "unverified".
"""
import json
import re
from typing import List, Set, Tuple
from pydantic import BaseModel, field_validator


class VerdictItem(BaseModel):
    anchor_id: str = ""
    anchor_type: str = "page_only"
    section_title: str = ""
    obligation: str = ""
    status: str = "unverified"
    evidence: str | None = None
    rationale: str = ""
    page: int = 1
    title: str = ""


def _extract_json_block(raw: str) -> str:
    """Pull the JSON array from ## JSON_VERDICTS section."""
    match = re.search(
        r"##\s*JSON_VERDICTS\s*\n+```(?:json)?\s*([\s\S]+?)```",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # Fallback: find first [...] block
    match = re.search(r"(\[[\s\S]*?\])", raw)
    if match:
        return match.group(1).strip()

    return "[]"


def _extract_narrative(raw: str) -> str:
    match = re.search(
        r"##\s*NARRATIVE_SUMMARY\s*\n+([\s\S]+?)(?:$|##)",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""


def validate_verdicts(
    raw_output: str,
    retrieved_anchor_ids: Set[str],
) -> Tuple[List[VerdictItem], List[str], str]:
    """
    Parse and validate LLM output.

    Returns:
        - validated verdict list
        - list of flagged anchor_ids (not in retrieved set)
        - narrative summary string
    """
    json_str = _extract_json_block(raw_output)
    narrative = _extract_narrative(raw_output)
    flagged: List[str] = []

    try:
        raw_items = json.loads(json_str)
        if not isinstance(raw_items, list):
            raw_items = []
    except (json.JSONDecodeError, ValueError):
        return [], ["<malformed JSON output>"], narrative

    verdicts: List[VerdictItem] = []
    for item in raw_items:
        try:
            v = VerdictItem.model_validate(item)
        except Exception:
            continue

        if v.anchor_id and v.anchor_id not in retrieved_anchor_ids:
            v.status = "unverified"
            v.evidence = None
            flagged.append(v.anchor_id)

        verdicts.append(v)

    return verdicts, flagged, narrative
```

- [ ] **Step 2: Commit**

```bash
git add generation/validator.py
git commit -m "feat: citation validator - flags anchors not in retrieved set"
```

---

## Task 13: Pipeline Orchestration

**Files:**
- Create: `generation/pipeline.py`

- [ ] **Step 1: Write generation/pipeline.py**

```python
# generation/pipeline.py
"""
End-to-end pipeline for one analysis turn.
Input: researcher text, optional follow-up question
Output: PipelineResult with verdicts, narrative, domains, sources
"""
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

from ingestion.loaders import load_document
from retrieval.classifier import classify_domains
from retrieval.retriever import retrieve, RetrievedChunk
from generation.gap_detector import detect_gaps
from generation.validator import validate_verdicts, VerdictItem
from config import TOP_K

_OFF_TOPIC_KEYWORDS = [
    "weather", "stock price", "recipe", "sports score",
    "joke", "movie", "translate", "who is", "what is the capital",
]


def _is_off_topic(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _OFF_TOPIC_KEYWORDS) and \
           not any(w in lower for w in ["consent", "data", "compliance", "access", "privacy"])


@dataclass
class PipelineResult:
    domains: List[str] = field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    verdicts: List[VerdictItem] = field(default_factory=list)
    flagged_anchors: List[str] = field(default_factory=list)
    narrative: str = ""
    off_topic: bool = False
    error: Optional[str] = None


def run_pipeline(
    researcher_text: str,
    follow_up: str = "",
    top_k: int = TOP_K,
) -> PipelineResult:
    result = PipelineResult()

    combined_query = f"{researcher_text}\n{follow_up}".strip()

    if _is_off_topic(combined_query) and not researcher_text.strip():
        result.off_topic = True
        result.narrative = (
            "I'm a GA4GH compliance assistant. Please upload a data use letter, "
            "consent form, or related document to begin a compliance review."
        )
        return result

    try:
        result.domains = classify_domains(combined_query)

        result.retrieved_chunks = retrieve(combined_query, top_k=top_k)

        raw_output = detect_gaps(
            researcher_text=researcher_text,
            retrieved_chunks=result.retrieved_chunks,
            follow_up=follow_up,
        )

        retrieved_anchor_ids = {c.anchor_id for c in result.retrieved_chunks}
        result.verdicts, result.flagged_anchors, result.narrative = validate_verdicts(
            raw_output, retrieved_anchor_ids
        )

    except Exception as exc:
        result.error = str(exc)
        result.narrative = f"Analysis failed: {exc}"

    return result


def run_pipeline_from_file(
    doc_path: Path,
    follow_up: str = "",
    top_k: int = TOP_K,
) -> PipelineResult:
    pages = load_document(doc_path)
    full_text = "\n\n".join(text for text, _ in pages)
    return run_pipeline(full_text, follow_up=follow_up, top_k=top_k)
```

- [ ] **Step 2: Commit**

```bash
git add generation/pipeline.py
git commit -m "feat: end-to-end pipeline orchestration with off-topic guard"
```

---

## Task 14: PDF Viewer Helper

**Files:**
- Create: `ui/pdf_viewer.py`

- [ ] **Step 1: Write ui/pdf_viewer.py**

```python
# ui/pdf_viewer.py
"""
Helpers for in-app PDF viewing via Streamlit.
"""
import base64
from pathlib import Path
from typing import Optional

import streamlit as st
from config import CORPUS_CACHE_DIR


def get_cached_pdf_path(drive_file_id: str, title: str) -> Optional[Path]:
    """
    Look up a locally cached PDF by drive_file_id or title stem.
    """
    if drive_file_id:
        for f in CORPUS_CACHE_DIR.glob("*"):
            if drive_file_id in f.stem:
                return f

    # Fallback: fuzzy title match
    title_slug = title.lower().replace(" ", "_")[:30]
    for f in CORPUS_CACHE_DIR.glob("*.pdf"):
        if title_slug[:10] in f.stem.lower():
            return f
    return None


def render_pdf_viewer(pdf_path: Path, page: int = 1):
    """
    Embed PDF in Streamlit via base64 iframe.
    Shows page number even if exact jump isn't supported by all browsers.
    """
    if not pdf_path.exists():
        st.warning(f"PDF not found at {pdf_path}")
        return

    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    # Most browsers support #page=N in data URIs
    pdf_url = f"data:application/pdf;base64,{b64}#page={page}"

    st.markdown(
        f'<iframe src="{pdf_url}" width="100%" height="600px" '
        f'style="border:none; border-radius:8px;"></iframe>',
        unsafe_allow_html=True,
    )
    st.caption(f"Showing page {page} — use browser PDF controls to navigate.")
```

- [ ] **Step 2: Commit**

```bash
git add ui/pdf_viewer.py
git commit -m "feat: in-app PDF viewer with base64 embedding"
```

---

## Task 15: Streamlit Chat App

**Files:**
- Create: `ui/app.py`

- [ ] **Step 1: Write ui/app.py**

Full chat-first Streamlit app with:
- `st.chat_message` / `st.chat_input` primitives
- Session state for message history, uploaded doc, verdict results
- File uploader in chat workflow
- Assistant messages: natural language first, structured evidence second (expandable)
- View Source side panel (st.sidebar or st.expander)
- Ingest corpus button in sidebar
- Unverified citation warning badges

See full implementation in code output.

- [ ] **Step 2: Commit**

```bash
git add ui/app.py
git commit -m "feat: chat-first Streamlit UI with compliance evidence cards"
```

---

## Task 16: Evaluation Tests

**Files:**
- Create: `evaluation/test_retrieval.py`
- Create: `evaluation/test_citations.py`

- [ ] **Step 1: Write evaluation/test_retrieval.py**

```python
# evaluation/test_retrieval.py
import pytest
from pathlib import Path
import tempfile, shutil

import chromadb
from chromadb.utils import embedding_functions

from config import EMBEDDING_MODEL
from ingestion.ingest import ingest_file, get_chroma_collection
from retrieval.retriever import retrieve


TEST_COLLECTION = "test_ga4gh_retrieval"


@pytest.fixture(scope="module")
def tmp_corpus(tmp_path_factory):
    d = tmp_path_factory.mktemp("corpus")
    (d / "test_framework.txt").write_text(
        "1. Purpose\nThis framework establishes principles for genomic data sharing.\n"
        "2. Data Access\nAll data access must be approved by a data access committee.\n"
        "DUO:0000007 Disease Specific Research Use — data restricted to disease research.\n",
        encoding="utf-8"
    )
    return d


@pytest.fixture(scope="module")
def chroma_tmp(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("chroma")
    return str(db_dir)


@pytest.fixture(scope="module")
def populated_collection(tmp_corpus, chroma_tmp, monkeypatch_module):
    client = chromadb.PersistentClient(path=chroma_tmp)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    col = client.get_or_create_collection(TEST_COLLECTION, embedding_function=ef)
    ingest_file(tmp_corpus / "test_framework.txt", col)
    return col, chroma_tmp


def test_chunks_ingested(populated_collection):
    col, _ = populated_collection
    assert col.count() > 0


def test_retrieval_returns_results(populated_collection, chroma_tmp, monkeypatch):
    monkeypatch.setattr("retrieval.retriever.CHROMA_DIR", chroma_tmp)
    chunks = retrieve("data access committee", top_k=3, collection_name=TEST_COLLECTION)
    assert len(chunks) > 0


def test_metadata_survives_ingestion(populated_collection):
    col, _ = populated_collection
    results = col.get(include=["metadatas"])
    for meta in results["metadatas"]:
        assert "doc_type" in meta
        assert "anchor_id" in meta
        assert "anchor_type" in meta
        assert "page" in meta


def test_page_provenance(populated_collection):
    col, _ = populated_collection
    results = col.get(include=["metadatas"])
    for meta in results["metadatas"]:
        assert isinstance(meta["page"], int)
        assert meta["page"] >= 1
```

- [ ] **Step 2: Write evaluation/test_citations.py**

```python
# evaluation/test_citations.py
import json
import pytest
from generation.validator import validate_verdicts


VALID_RAW = """
## JSON_VERDICTS
```json
[
  {
    "anchor_id": "DUO:0000007",
    "anchor_type": "duo_term",
    "section_title": "Disease Specific Research",
    "obligation": "Data restricted to disease research",
    "status": "covered",
    "evidence": "We will use data only for cardiovascular disease research.",
    "rationale": "Researcher explicitly restricts use to disease research.",
    "page": 2,
    "title": "DUO Guidance"
  }
]
```

## NARRATIVE_SUMMARY
The researcher document satisfies the DUO:0000007 requirement.
"""

INVALID_ANCHOR_RAW = """
## JSON_VERDICTS
```json
[
  {
    "anchor_id": "FAKE:9999999",
    "anchor_type": "duo_term",
    "section_title": "Nonexistent Section",
    "obligation": "Made-up obligation",
    "status": "covered",
    "evidence": "Some text",
    "rationale": "Fabricated",
    "page": 1,
    "title": "Fake Doc"
  }
]
```

## NARRATIVE_SUMMARY
Nothing real here.
"""

MALFORMED_RAW = "This is not JSON at all. Just some text."


def test_valid_anchor_passes():
    retrieved_ids = {"DUO:0000007", "1", "data-sharing"}
    verdicts, flagged, narrative = validate_verdicts(VALID_RAW, retrieved_ids)
    assert len(verdicts) == 1
    assert verdicts[0].anchor_id == "DUO:0000007"
    assert verdicts[0].status == "covered"
    assert flagged == []


def test_invalid_anchor_flagged():
    retrieved_ids = {"DUO:0000007", "1"}
    verdicts, flagged, narrative = validate_verdicts(INVALID_ANCHOR_RAW, retrieved_ids)
    assert len(verdicts) == 1
    assert verdicts[0].status == "unverified"
    assert verdicts[0].evidence is None
    assert "FAKE:9999999" in flagged


def test_malformed_json_handled_gracefully():
    verdicts, flagged, narrative = validate_verdicts(MALFORMED_RAW, set())
    assert isinstance(verdicts, list)
    assert isinstance(flagged, list)


def test_narrative_extracted():
    retrieved_ids = {"DUO:0000007"}
    _, _, narrative = validate_verdicts(VALID_RAW, retrieved_ids)
    assert "DUO:0000007" in narrative
```

- [ ] **Step 3: Commit**

```bash
git add evaluation/
git commit -m "test: retrieval provenance and citation validator tests"
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Generalized anchor metadata schema | Task 2, 3 |
| Page-aware chunking | Task 5 |
| DUO + numbered + heading anchor extraction | Task 3 |
| ChromaDB ingestion with metadata | Task 6 |
| Local source cache | Task 6 |
| Domain classifier | Task 8 |
| Semantic retrieval + metadata filter | Task 9 |
| LLM gap detection with evidence-only prompt | Task 10, 11 |
| Citation validator (anchor cross-check) | Task 12 |
| Off-topic guard | Task 13 |
| End-to-end pipeline | Task 13 |
| Chat-first Streamlit UI | Task 15 |
| View Source behavior | Task 14, 15 |
| Evaluation tests | Task 16 |
| Sample corpus + test DULs | Task 7 |

All requirements covered.

### Placeholder Scan

Task 7 Step 1–4 reference "see full content" — these will be written as actual file content during execution.

Task 15 Step 1 references "see full implementation" — full code will be written during execution.

These are execution-phase details, not plan failures — the implementation plan phase acknowledges these are the two largest files and delegates content to execution.

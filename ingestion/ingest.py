# ingestion/ingest.py
"""
Ingestion orchestration.
Usage: python -m ingestion.ingest
       python -m ingestion.ingest --corpus-dir data/ga4gh_corpus
"""
import argparse
import shutil
import uuid
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from config import (
    CHROMA_DIR,
    CORPUS_CACHE_DIR,
    CORPUS_COLLECTION,
    CORPUS_DIR,
    EMBEDDING_MODEL,
)
from ingestion.chunker import chunk_pages
from ingestion.loaders import load_document
from ingestion.metadata import DocType

# Heuristic doc_type assignment by filename keywords (checked in order)
_DOC_TYPE_HINTS: list[tuple[list[str], DocType]] = [
    (["duo", "machine readable", "machine-readable", "consent guidance"], "guideline"),
    (["clause", "template", "pediatric", "familial", "clinical", "clause bank"], "template_clause_bank"),
    (["ethics", "irb", "research ethics"], "ethics_policy"),
    (["position", "statement"], "position_statement"),
    (["tool", "reference", "api", "tooling"], "tooling_reference"),
    (["framework", "policy framework", "lexicon", "sharing", "responsible"], "framework"),
]


def infer_doc_type(path: Path) -> DocType:
    name_lower = path.stem.lower().replace("-", " ").replace("_", " ")
    for keywords, doc_type in _DOC_TYPE_HINTS:
        if any(kw in name_lower for kw in keywords):
            return doc_type
    return "framework"


def get_chroma_collection(
    collection_name: str = CORPUS_COLLECTION,
    chroma_dir: Optional[str] = None,
):
    """Return (or create) a ChromaDB collection with sentence-transformer embeddings."""
    client = chromadb.PersistentClient(path=str(chroma_dir or CHROMA_DIR))
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
    """
    Ingest a single file into a ChromaDB collection.
    Returns the number of chunks added.
    Also copies the source file into the local cache folder.
    """
    if doc_type is None:
        doc_type = infer_doc_type(path)

    title = path.stem.replace("-", " ").replace("_", " ").title()
    pages = load_document(path)
    chunks = chunk_pages(
        pages,
        doc_type=doc_type,
        title=title,
        source_url=source_url,
        drive_file_id=drive_file_id,
    )

    if not chunks:
        return 0

    texts = [c[0] for c in chunks]
    metadatas = [c[1].to_chroma_dict() for c in chunks]
    ids = [f"{path.stem}_{uuid.uuid4().hex[:8]}" for _ in chunks]

    collection.add(documents=texts, metadatas=metadatas, ids=ids)

    # Cache source file so the UI PDF viewer can serve it
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CORPUS_CACHE_DIR / path.name
    if not dest.exists():
        shutil.copy2(path, dest)

    return len(chunks)


def ingest_corpus(corpus_dir: Path = CORPUS_DIR) -> int:
    """
    Ingest all PDF/TXT files in corpus_dir.
    Returns total number of chunks ingested.
    """
    collection = get_chroma_collection()
    total = 0
    supported = {".pdf", ".txt", ".md"}
    for path in sorted(corpus_dir.glob("*")):
        if path.suffix.lower() in supported and path.is_file():
            n = ingest_file(path, collection)
            print(f"  Ingested {path.name}: {n} chunks")
            total += n
    print(f"\nTotal chunks ingested: {total}")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest GA4GH corpus into ChromaDB")
    parser.add_argument(
        "--corpus-dir",
        default=str(CORPUS_DIR),
        help="Path to corpus directory (default: data/ga4gh_corpus)",
    )
    args = parser.parse_args()
    ingest_corpus(Path(args.corpus_dir))

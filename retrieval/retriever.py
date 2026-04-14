# retrieval/retriever.py
"""
Semantic retrieval from ChromaDB with optional metadata filtering.
"""
from dataclasses import dataclass, field
from typing import List, Optional

import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_DIR, CORPUS_COLLECTION, EMBEDDING_MODEL, TOP_K
from ingestion.metadata import DocType


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
    score: float  # cosine similarity (0–1, higher = more similar)


def _get_collection(collection_name: str, chroma_dir: Optional[str] = None):
    client = chromadb.PersistentClient(path=str(chroma_dir or CHROMA_DIR))
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
    chroma_dir: Optional[str] = None,
) -> List[RetrievedChunk]:
    """
    Semantic similarity retrieval.
    Optionally filters by doc_type metadata field.
    Returns up to top_k RetrievedChunk objects ordered by similarity.
    """
    collection = _get_collection(collection_name, chroma_dir)
    count = collection.count()
    if count == 0:
        return []

    where = {"doc_type": {"$eq": doc_type_filter}} if doc_type_filter else None

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, count),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks: List[RetrievedChunk] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, distances):
        chunks.append(
            RetrievedChunk(
                text=doc,
                anchor_id=meta.get("anchor_id", ""),
                anchor_type=meta.get("anchor_type", "page_only"),
                section_title=meta.get("section_title", ""),
                page=int(meta.get("page", 1)),
                source_url=meta.get("source_url", ""),
                title=meta.get("title", ""),
                drive_file_id=meta.get("drive_file_id", ""),
                doc_type=meta.get("doc_type", ""),
                score=max(0.0, 1.0 - float(dist)),
            )
        )

    return chunks

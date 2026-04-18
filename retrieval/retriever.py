"""
Semantic retrieval from ChromaDB with optional metadata filtering.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_DIR, CORPUS_COLLECTION, EMBEDDING_MODEL, MANIFEST_PATH, TOP_K
from ingestion.manifest import SourceConfig, load_manifest
from ingestion.metadata import DocType


@dataclass
class RetrievedChunk:
    text: str
    article_id: str
    article_scheme: str
    section_title: str
    page: int | None
    source_url: str
    source_title: str
    source_id: str
    framework_domain: str
    chunk_index: int
    doc_type: str
    score: float


_LEGACY_SCHEME_MAP = {
    "duo_term": "duo",
    "numbered_section": "page_only",
    "section_heading": "page_only",
    "page_only": "page_only",
}


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


def _normalize_text(value: str) -> str:
    return value.strip().lower().rstrip("/")


@lru_cache(maxsize=1)
def _load_manifest_sources() -> list[SourceConfig]:
    try:
        return load_manifest(MANIFEST_PATH)
    except Exception:
        return []


def _match_manifest_source(
    source_id: str,
    source_title: str,
    source_url: str,
    article_id: str,
    article_scheme: str,
) -> SourceConfig | None:
    sources = _load_manifest_sources()
    if not sources:
        return None

    if source_id:
        for source in sources:
            if source.id == source_id:
                return source

    normalized_url = _normalize_text(source_url) if source_url else ""
    if normalized_url:
        for source in sources:
            candidate_urls = [source.url]
            if source.landing_url:
                candidate_urls.append(source.landing_url)
            if normalized_url in {_normalize_text(url) for url in candidate_urls}:
                return source

    normalized_title = _normalize_text(source_title) if source_title else ""
    if normalized_title:
        for source in sources:
            if _normalize_text(source.title) == normalized_title:
                return source

    if article_id.upper().startswith("DUO:") or article_scheme == "duo":
        for source in sources:
            if source.id == "duo":
                return source

    return None


def _coerce_page(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_metadata(meta: dict) -> dict:
    article_id = str(meta.get("article_id") or meta.get("anchor_id") or "").strip()
    article_scheme = str(
        meta.get("article_scheme")
        or _LEGACY_SCHEME_MAP.get(str(meta.get("anchor_type", "")).strip(), "")
        or "page_only"
    ).strip()
    source_title = str(meta.get("source_title") or meta.get("title") or "").strip()
    source_url = str(meta.get("source_url") or "").strip()
    source_id = str(meta.get("source_id") or "").strip()
    framework_domain = str(meta.get("framework_domain") or "").strip()

    matched_source = _match_manifest_source(
        source_id=source_id,
        source_title=source_title,
        source_url=source_url,
        article_id=article_id,
        article_scheme=article_scheme,
    )
    if matched_source:
        source_id = source_id or matched_source.id
        source_title = source_title or matched_source.title
        source_url = source_url or matched_source.landing_url or matched_source.url
        framework_domain = framework_domain or matched_source.framework_domain
        if article_scheme == "page_only":
            article_scheme = matched_source.article_scheme

    return {
        "article_id": article_id,
        "article_scheme": article_scheme or "page_only",
        "section_title": str(meta.get("section_title") or "").strip(),
        "page": _coerce_page(meta.get("page")),
        "source_url": source_url,
        "source_title": source_title,
        "source_id": source_id,
        "framework_domain": framework_domain,
        "chunk_index": int(meta.get("chunk_index", 0) or 0),
        "doc_type": str(meta.get("doc_type") or "").strip(),
    }


def retrieve(
    query: str,
    top_k: int = TOP_K,
    doc_type_filter: Optional[DocType] = None,
    collection_name: str = CORPUS_COLLECTION,
    chroma_dir: Optional[str] = None,
) -> list[RetrievedChunk]:
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

    chunks: list[RetrievedChunk] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, distances):
        resolved = _resolve_metadata(meta)
        chunks.append(
            RetrievedChunk(
                text=doc,
                article_id=resolved["article_id"],
                article_scheme=resolved["article_scheme"],
                section_title=resolved["section_title"],
                page=resolved["page"],
                source_url=resolved["source_url"],
                source_title=resolved["source_title"],
                source_id=resolved["source_id"],
                framework_domain=resolved["framework_domain"],
                chunk_index=resolved["chunk_index"],
                doc_type=resolved["doc_type"],
                score=max(0.0, 1.0 - float(dist)),
            )
        )

    return chunks

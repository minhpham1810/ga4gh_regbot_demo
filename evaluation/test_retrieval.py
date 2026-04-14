# evaluation/test_retrieval.py
"""
Tests for ingestion pipeline + retrieval.
Verifies: chunks are ingested, retrieval works, metadata survives round-trip.
Uses an isolated tmp ChromaDB so it does not touch the production chroma_db/.
"""
import pytest
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

from config import EMBEDDING_MODEL
from ingestion.ingest import ingest_file
from ingestion.metadata import ChunkMetadata
from retrieval.retriever import retrieve

TEST_COLLECTION = "test_retrieval_collection"


@pytest.fixture(scope="module")
def tmp_corpus(tmp_path_factory):
    """Create a minimal corpus directory with one sample text file."""
    d = tmp_path_factory.mktemp("corpus")
    (d / "test_framework.txt").write_text(
        "1. Purpose\n"
        "This framework establishes principles for genomic data sharing.\n\n"
        "2. Data Access\n"
        "All data access must be approved by a data access committee.\n\n"
        "DUO:0000007 Disease Specific Research Use — data restricted to disease research.\n\n"
        "Data Sharing\n"
        "Data may be shared under open or controlled access terms.\n",
        encoding="utf-8",
    )
    return d


@pytest.fixture(scope="module")
def chroma_tmp(tmp_path_factory):
    """Isolated ChromaDB directory for tests."""
    return str(tmp_path_factory.mktemp("chroma"))


@pytest.fixture(scope="module")
def collection_and_dir(tmp_corpus, chroma_tmp):
    """Ingest the sample corpus into an isolated collection. Return (collection, chroma_dir)."""
    client = chromadb.PersistentClient(path=chroma_tmp)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    col = client.get_or_create_collection(
        TEST_COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    ingest_file(tmp_corpus / "test_framework.txt", col)
    return col, chroma_tmp


class TestIngestion:
    def test_chunks_are_ingested(self, collection_and_dir):
        col, _ = collection_and_dir
        assert col.count() > 0, "Expected at least one chunk after ingestion"

    def test_metadata_has_required_fields(self, collection_and_dir):
        col, _ = collection_and_dir
        results = col.get(include=["metadatas"])
        assert results["metadatas"], "Expected metadata in collection"
        for meta in results["metadatas"]:
            assert "doc_type" in meta, f"doc_type missing from: {meta}"
            assert "anchor_id" in meta, f"anchor_id missing from: {meta}"
            assert "anchor_type" in meta, f"anchor_type missing from: {meta}"
            assert "page" in meta, f"page missing from: {meta}"

    def test_page_provenance_is_integer(self, collection_and_dir):
        col, _ = collection_and_dir
        results = col.get(include=["metadatas"])
        for meta in results["metadatas"]:
            assert isinstance(meta["page"], int), f"page should be int, got {type(meta['page'])}"
            assert meta["page"] >= 1, "page should be 1-indexed"

    def test_anchor_id_is_non_empty(self, collection_and_dir):
        col, _ = collection_and_dir
        results = col.get(include=["metadatas"])
        for meta in results["metadatas"]:
            assert meta["anchor_id"] != "", "anchor_id should never be empty"


class TestRetrieval:
    def test_retrieval_returns_results(self, collection_and_dir, monkeypatch):
        _, chroma_dir = collection_and_dir
        # Patch CHROMA_DIR and collection name for the retriever
        import retrieval.retriever as rmod
        monkeypatch.setattr(rmod, "CHROMA_DIR", chroma_dir)

        chunks = retrieve(
            "data access committee genomic",
            top_k=3,
            collection_name=TEST_COLLECTION,
            chroma_dir=chroma_dir,
        )
        assert len(chunks) > 0, "Expected at least one retrieved chunk"

    def test_retrieved_chunk_has_anchor_id(self, collection_and_dir, monkeypatch):
        _, chroma_dir = collection_and_dir
        import retrieval.retriever as rmod
        monkeypatch.setattr(rmod, "CHROMA_DIR", chroma_dir)

        chunks = retrieve(
            "disease specific research use",
            top_k=3,
            collection_name=TEST_COLLECTION,
            chroma_dir=chroma_dir,
        )
        for chunk in chunks:
            assert chunk.anchor_id != "", "Retrieved chunk must have non-empty anchor_id"
            assert isinstance(chunk.page, int)
            assert chunk.doc_type != ""

    def test_empty_corpus_returns_empty_list(self, tmp_path):
        """Retrieval against an empty collection should return [] not raise."""
        empty_dir = str(tmp_path / "empty_chroma")
        chunks = retrieve(
            "anything",
            top_k=5,
            collection_name="empty_test_col",
            chroma_dir=empty_dir,
        )
        assert chunks == []

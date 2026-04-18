"""
Tests for ingestion pipeline plus retrieval.
Verifies: chunks are produced, retrieval works, metadata survives round-trip.
"""
from dataclasses import dataclass

from langchain_core.documents import Document

from ingestion.chunker import chunk_documents
from ingestion.manifest import SourceConfig
from ingestion.metadata import base_metadata, enrich
from retrieval.retriever import retrieve

TEST_COLLECTION = "test_retrieval_collection"


@dataclass
class FakeCollection:
    documents: list[str]
    metadatas: list[dict]

    def count(self) -> int:
        return len(self.documents)

    def get(self, include=None) -> dict:
        return {"metadatas": self.metadatas}

    def query(self, query_texts, n_results, where=None, include=None) -> dict:
        query = query_texts[0].lower()
        tokens = [token for token in query.split() if token]
        ranked: list[tuple[int, str, dict]] = []
        for document, metadata in zip(self.documents, self.metadatas):
            if where and metadata.get("doc_type") != where["doc_type"]["$eq"]:
                continue
            score = sum(token in document.lower() for token in tokens)
            ranked.append((score, document, metadata))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = ranked[:n_results]
        docs = [item[1] for item in selected]
        metas = [item[2] for item in selected]
        distances = [1.0 - (item[0] / max(len(tokens), 1)) for item in selected]
        return {"documents": [docs], "metadatas": [metas], "distances": [distances]}


def _build_chunked_docs() -> list[Document]:
    source = SourceConfig(
        id="frs_test",
        title="Test Framework",
        source_kind="pdf",
        url="https://example.test/framework.pdf",
        landing_url="https://example.test/framework",
        doc_type="framework",
        framework_domain="responsible_sharing",
        article_scheme="frs",
    )
    page_docs = [
        Document(
            page_content="Section 1 Purpose\nThis framework establishes principles for genomic data sharing.",
            metadata={"page": 1, "section_title": ""},
        ),
        Document(
            page_content="Section 2 Data Access\nAll data access must be approved by a data access committee.",
            metadata={"page": 2, "section_title": ""},
        ),
        Document(
            page_content=(
                "Section 4.3 Disease Specific Research\n"
                "DUO:0000007 Disease Specific Research Use restricts use to disease-specific research."
            ),
            metadata={"page": 3, "section_title": ""},
        ),
    ]
    enriched_docs = [enrich(doc, base_metadata(source)) for doc in page_docs]
    return chunk_documents(enriched_docs)


def _build_collection() -> FakeCollection:
    chunked_docs = _build_chunked_docs()
    return FakeCollection(
        documents=[doc.page_content for doc in chunked_docs],
        metadatas=[doc.metadata for doc in chunked_docs],
    )


class TestIngestion:
    def test_chunks_are_ingested(self):
        collection = _build_collection()
        assert collection.count() > 0

    def test_metadata_has_required_fields(self):
        collection = _build_collection()
        results = collection.get(include=["metadatas"])
        assert results["metadatas"]
        for meta in results["metadatas"]:
            assert "doc_type" in meta
            assert "article_id" in meta
            assert "article_scheme" in meta
            assert "source_id" in meta
            assert "page" in meta

    def test_page_provenance_is_integer(self):
        collection = _build_collection()
        results = collection.get(include=["metadatas"])
        for meta in results["metadatas"]:
            assert isinstance(meta["page"], int)
            assert meta["page"] >= 1

    def test_article_id_is_non_empty(self):
        collection = _build_collection()
        results = collection.get(include=["metadatas"])
        for meta in results["metadatas"]:
            assert meta["article_id"] != ""


class TestRetrieval:
    def test_retrieval_returns_results(self, monkeypatch):
        import retrieval.retriever as retriever_module

        monkeypatch.setattr(retriever_module, "_get_collection", lambda *args, **kwargs: _build_collection())
        chunks = retrieve(
            "data access committee genomic",
            top_k=3,
            collection_name=TEST_COLLECTION,
            chroma_dir="ignored",
        )
        assert len(chunks) > 0

    def test_retrieved_chunk_has_article_id(self, monkeypatch):
        import retrieval.retriever as retriever_module

        monkeypatch.setattr(retriever_module, "_get_collection", lambda *args, **kwargs: _build_collection())
        chunks = retrieve(
            "disease specific research use",
            top_k=3,
            collection_name=TEST_COLLECTION,
            chroma_dir="ignored",
        )
        for chunk in chunks:
            assert chunk.article_id != ""
            assert isinstance(chunk.page, int)
            assert chunk.doc_type != ""
            assert chunk.source_title != ""
            assert chunk.source_id != ""

    def test_empty_corpus_returns_empty_list(self, monkeypatch):
        import retrieval.retriever as retriever_module

        monkeypatch.setattr(retriever_module, "_get_collection", lambda *args, **kwargs: FakeCollection([], []))
        chunks = retrieve(
            "anything",
            top_k=5,
            collection_name="empty_test_col",
            chroma_dir="ignored",
        )
        assert chunks == []

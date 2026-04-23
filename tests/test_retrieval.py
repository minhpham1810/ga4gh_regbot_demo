from dataclasses import dataclass

from langchain_core.documents import Document

from ingestion.chunker import chunk_documents
from ingestion.manifest import SourceConfig
from ingestion.metadata import base_metadata, enrich
from retrieval.retriever import retrieve


@dataclass
class FakeCollection:
    documents: list[str]
    metadatas: list[dict]

    def count(self) -> int:
        return len(self.documents)

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


def _build_collection() -> FakeCollection:
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
    chunked_docs = chunk_documents([enrich(doc, base_metadata(source)) for doc in page_docs])
    return FakeCollection(
        documents=[doc.page_content for doc in chunked_docs],
        metadatas=[doc.metadata for doc in chunked_docs],
    )


def test_retrieve_returns_metadata_aware_chunks(monkeypatch):
    import retrieval.retriever as retriever_module

    monkeypatch.setattr(retriever_module, "_get_collection", lambda *args, **kwargs: _build_collection())
    chunks = retrieve("disease specific research use", top_k=2, chroma_dir="ignored")
    assert chunks
    assert chunks[0].article_id != ""
    assert chunks[0].source_id == "frs_test"
    assert chunks[0].source_title == "Test Framework"
    assert isinstance(chunks[0].page, int)

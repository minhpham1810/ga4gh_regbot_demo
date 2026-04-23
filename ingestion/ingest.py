import argparse
from pathlib import Path

from langchain_core.documents import Document

from config import CHROMA_DIR, CORPUS_COLLECTION, CORPUS_RAW_DIR, MANIFEST_PATH
from ingestion.chunker import chunk_documents
from ingestion.loaders import fetch_if_missing
from ingestion.manifest import SourceConfig, load_manifest
from ingestion.metadata import base_metadata, enrich
from ingestion.parsers import parse_duo_owl, parse_pdf


def _parse_source(raw_path: Path, source: SourceConfig) -> list[Document]:
    if source.source_kind == "pdf":
        return parse_pdf(raw_path, source)
    if source.source_kind == "owl":
        return parse_duo_owl(raw_path, source)
    raise ValueError(f"Unsupported source_kind: {source.source_kind}")


def ingest_corpus(
    manifest_path: Path = MANIFEST_PATH,
    raw_dir: Path = CORPUS_RAW_DIR,
) -> list[Document]:
    chunked_documents: list[Document] = []
    for source in load_manifest(manifest_path):
        raw_path = fetch_if_missing(source, raw_dir)
        parsed_docs = _parse_source(raw_path, source)
        enriched_docs = [enrich(doc, base_metadata(source)) for doc in parsed_docs]
        chunked_documents.extend(chunk_documents(enriched_docs))
    return chunked_documents


def ingest_corpus_with_report(
    manifest_path: Path = MANIFEST_PATH,
    raw_dir: Path = CORPUS_RAW_DIR,
) -> tuple[list[Document], list[dict]]:
    chunked_documents: list[Document] = []
    report: list[dict] = []
    for source in load_manifest(manifest_path):
        raw_path = fetch_if_missing(source, raw_dir)
        parsed_docs = _parse_source(raw_path, source)
        enriched_docs = [enrich(doc, base_metadata(source)) for doc in parsed_docs]
        source_chunks = chunk_documents(enriched_docs)
        chunked_documents.extend(source_chunks)
        report.append(
            {
                "source_id": source.id,
                "source_kind": source.source_kind,
                "document_count": len(enriched_docs),
                "chunk_count": len(source_chunks),
                "raw_path": raw_path,
            }
        )
    return chunked_documents, report


def persist_to_chroma(
    documents: list[Document],
    chroma_dir: Path = CHROMA_DIR,
    collection_name: str = CORPUS_COLLECTION,
) -> None:
    print(
        "Chroma persistence is not implemented in this repository yet. "
        f"Parsed {len(documents)} documents for collection '{collection_name}' in "
        f"'{chroma_dir}'."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and parse the GA4GH corpus.")
    parser.add_argument(
        "--manifest-path",
        default=str(MANIFEST_PATH),
        help="Path to the corpus manifest YAML.",
    )
    parser.add_argument(
        "--raw-dir",
        default=str(CORPUS_RAW_DIR),
        help="Directory for raw source byte caching.",
    )
    args = parser.parse_args()

    documents, report = ingest_corpus_with_report(
        manifest_path=Path(args.manifest_path),
        raw_dir=Path(args.raw_dir),
    )
    for item in report:
        print(
            f"[{item['source_id']}] {item['document_count']} documents -> "
            f"{item['chunk_count']} chunks"
        )
    print(f"\nTotal chunks: {len(documents)}")

# ingestion/chunker.py
"""
Page-aware chunking.
Splits within a page; never crosses page boundaries.
Returns list of (chunk_text, ChunkMetadata).
"""
from typing import List, Tuple

from ingestion.loaders import PageChunk
from ingestion.metadata import ChunkMetadata, DocType
from ingestion.anchors import extract_anchor
from config import CHUNK_SIZE, CHUNK_OVERLAP


def _split_text(text: str, size: int, overlap: int) -> List[str]:
    """Character-level sliding-window split."""
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
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
    Chunking stays within a single page to preserve page provenance.
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

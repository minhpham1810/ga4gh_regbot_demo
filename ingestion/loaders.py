# ingestion/loaders.py
"""
Load PDF and TXT files.
Returns list of (page_text, page_number) tuples — page_number is 1-indexed.
"""
from pathlib import Path
from typing import List, Tuple

PageChunk = Tuple[str, int]  # (text, 1-indexed page number)


def load_pdf(path: Path) -> List[PageChunk]:
    """Extract text per page from a PDF using PyMuPDF (fitz)."""
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
    """Load a text file as a single logical page."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [(text, 1)]


def load_document(path: Path) -> List[PageChunk]:
    """Dispatch to the appropriate loader based on file suffix."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    elif suffix in (".txt", ".md"):
        return load_txt(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix!r}")

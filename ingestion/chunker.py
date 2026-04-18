import re
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from slugify import slugify

from config import CHUNK_OVERLAP, CHUNK_SIZE
from ingestion.metadata import enrich

_FRS_NUMBERED_RE = re.compile(
    r"(?im)^\s*(?:section|article)\s+(\d+(?:\.\d+)*)\b(?:[:.\-\s]+(.{1,120}))?"
)
_FRS_INLINE_RE = re.compile(r"(?im)^\s*(\d+(?:\.\d+)*)[.\s:-]+(.{1,120})$")
_HEADING_RE = re.compile(r"^[A-Z][A-Za-z0-9,()'\"/&:;\- ]{2,120}$")


@dataclass
class ArticleMatch:
    article_id: str
    section_title: str = ""


def extract_frs_section_id(text: str) -> ArticleMatch | None:
    match = _FRS_NUMBERED_RE.search(text)
    if match:
        return ArticleMatch(
            article_id=match.group(1).strip(),
            section_title=(match.group(2) or "").strip(),
        )

    match = _FRS_INLINE_RE.search(text)
    if match:
        return ArticleMatch(
            article_id=match.group(1).strip(),
            section_title=(match.group(2) or "").strip(),
        )

    return None


def extract_consent_clause_id(text: str) -> ArticleMatch | None:
    candidate_lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in candidate_lines[:12]:
        if len(line) > 140:
            continue
        if line.endswith("."):
            continue
        if line.lower().startswith("page "):
            continue
        if _HEADING_RE.match(line):
            return ArticleMatch(article_id=slugify(line), section_title=line)
    return None


def _fallback_article_id(doc: Document) -> str:
    source_id = doc.metadata.get("source_id", "source")
    page = doc.metadata.get("page")
    if page is not None:
        return f"{source_id}:p{page}"
    return source_id


def _base_article_metadata(doc: Document) -> dict:
    scheme = doc.metadata.get("article_scheme", "page_only")
    if scheme == "duo":
        return {
            "article_id": doc.metadata.get("article_id", ""),
            "article_scheme": "duo",
            "section_title": doc.metadata.get("section_title", ""),
        }

    if scheme == "frs":
        match = extract_frs_section_id(doc.page_content)
        if match:
            return {
                "article_id": match.article_id,
                "article_scheme": "frs",
                "section_title": doc.metadata.get("section_title") or match.section_title,
            }

    if scheme == "consent_clause":
        match = extract_consent_clause_id(doc.page_content)
        if match:
            return {
                "article_id": match.article_id,
                "article_scheme": "consent_clause",
                "section_title": doc.metadata.get("section_title") or match.section_title,
            }

    return {
        "article_id": _fallback_article_id(doc),
        "article_scheme": "page_only",
        "section_title": doc.metadata.get("section_title", ""),
    }


def chunk_documents(
    docs: list[Document],
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    chunked: list[Document] = []

    for doc in docs:
        article_meta = _base_article_metadata(doc)
        if doc.metadata.get("article_scheme") == "duo":
            chunked.append(enrich(doc, {**article_meta, "chunk_index": 0}))
            continue

        for index, text in enumerate(splitter.split_text(doc.page_content)):
            if not text.strip():
                continue
            chunked.append(
                Document(
                    page_content=text,
                    metadata={**doc.metadata, **article_meta, "chunk_index": index},
                )
            )

    return chunked

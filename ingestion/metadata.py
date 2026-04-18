from typing import Literal

from langchain_core.documents import Document
from pydantic import BaseModel

from ingestion.manifest import SourceConfig

DocType = Literal["framework", "ontology", "consent_toolkit"]
ArticleScheme = Literal["frs", "duo", "consent_clause", "page_only"]
FrameworkDomain = Literal["responsible_sharing", "data_use", "consent"]


class ChunkMetadata(BaseModel):
    source_id: str
    source_title: str
    source_url: str
    doc_type: DocType
    framework_domain: FrameworkDomain
    article_id: str = ""
    article_scheme: ArticleScheme = "page_only"
    section_title: str = ""
    page: int | None = None
    chunk_index: int = 0

    def to_chroma_dict(self) -> dict:
        return {key: value for key, value in self.model_dump().items() if value is not None}


def base_metadata(source: SourceConfig) -> dict:
    return {
        "source_id": source.id,
        "source_title": source.title,
        "source_url": source.landing_url or source.url,
        "doc_type": source.doc_type,
        "framework_domain": source.framework_domain,
        "article_scheme": source.article_scheme,
    }


def enrich(doc: Document, extra: dict) -> Document:
    return Document(
        page_content=doc.page_content,
        metadata={**doc.metadata, **extra},
    )

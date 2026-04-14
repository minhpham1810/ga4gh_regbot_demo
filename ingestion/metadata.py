# ingestion/metadata.py
from typing import Literal, Optional
from pydantic import BaseModel

DocType = Literal[
    "framework",
    "guideline",
    "template_clause_bank",
    "ethics_policy",
    "position_statement",
    "tooling_reference",
]

AnchorType = Literal[
    "numbered_section",
    "duo_term",
    "section_heading",
    "page_only",
]


class ChunkMetadata(BaseModel):
    doc_type: DocType
    anchor_id: str
    anchor_type: AnchorType
    section_title: str = ""
    source_url: str = ""
    page: int = 1
    start_page: int = 1
    end_page: int = 1
    title: str = ""
    drive_file_id: str = ""

    def to_chroma_dict(self) -> dict:
        """Flat dict safe for ChromaDB metadata (no None values)."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


def make_page_fallback_metadata(
    page: int,
    title: str,
    doc_type: DocType,
    source_url: str = "",
    drive_file_id: str = "",
) -> ChunkMetadata:
    return ChunkMetadata(
        doc_type=doc_type,
        anchor_id=str(page),
        anchor_type="page_only",
        section_title="",
        source_url=source_url,
        page=page,
        start_page=page,
        end_page=page,
        title=title,
        drive_file_id=drive_file_id,
    )

# ingestion/anchors.py
"""
Anchor extraction with priority: DUO term > numbered clause > heading > page fallback.
"""
import re
from dataclasses import dataclass
from slugify import slugify


@dataclass
class AnchorResult:
    anchor_id: str
    anchor_type: str  # "duo_term" | "numbered_section" | "section_heading" | "page_only"
    section_title: str


_DUO_RE = re.compile(r"\bDUO:\d{7}\b")

# Matches: "1. Title", "2.3 Title", "Section 3", "Clause 4.1 Title"
_NUMBERED_RE = re.compile(
    r"^(?:(?:Section|Clause|Article)\s+)?(\d+(?:\.\d+)*)[.\s:\-]+(.{3,80})",
    re.IGNORECASE | re.MULTILINE,
)

# Standalone title-case or ALL-CAPS line (3–60 chars, no sentence-ending punctuation)
_HEADING_RE = re.compile(
    r"^([A-Z][A-Za-z0-9 /\-]{3,60})$",
    re.MULTILINE,
)


def extract_anchor(text: str, page: int) -> AnchorResult:
    """Return the best citation anchor from a text chunk."""

    # 1. DUO term takes absolute priority
    duo_match = _DUO_RE.search(text)
    if duo_match:
        return AnchorResult(
            anchor_id=duo_match.group(),
            anchor_type="duo_term",
            section_title=duo_match.group(),
        )

    # 2. Numbered clause / section
    num_match = _NUMBERED_RE.search(text)
    if num_match:
        num = num_match.group(1).strip()
        title = num_match.group(2).strip()[:80]
        return AnchorResult(
            anchor_id=num,
            anchor_type="numbered_section",
            section_title=title,
        )

    # 3. Nearest standalone heading
    heading_match = _HEADING_RE.search(text)
    if heading_match:
        heading = heading_match.group(1).strip()
        return AnchorResult(
            anchor_id=slugify(heading),
            anchor_type="section_heading",
            section_title=heading,
        )

    # 4. Page-only fallback
    return AnchorResult(
        anchor_id=str(page),
        anchor_type="page_only",
        section_title="",
    )

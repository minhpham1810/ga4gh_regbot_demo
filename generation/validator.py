"""Helpers for validating cited article IDs against retrieved evidence."""

import json
import re

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

_JSON_BLOCK_PATTERNS = (
    re.compile(r"##\s*JSON_VERDICTS\s*\n+```(?:json)?\s*([\s\S]+?)```", re.IGNORECASE),
    re.compile(r"##\s*JSON_VERDICTS\s*\n+(\[[\s\S]*?\])", re.IGNORECASE),
    re.compile(r"(\[[\s\S]*?\])"),
)
_NARRATIVE_PATTERN = re.compile(
    r"##\s*NARRATIVE_SUMMARY\s*\n+([\s\S]+?)(?:\Z|(?=##\s))",
    re.IGNORECASE,
)
_INLINE_CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")


class VerdictItem(BaseModel):
    """One structured obligation verdict returned by the review model."""

    model_config = ConfigDict(populate_by_name=True)

    article_id: str = Field(
        default="",
        validation_alias=AliasChoices("article_id", "anchor_id"),
    )
    article_scheme: str = Field(
        default="page_only",
        validation_alias=AliasChoices("article_scheme", "anchor_type"),
    )
    section_title: str = ""
    obligation: str = ""
    status: str = "unverified"
    evidence: str | None = None
    rationale: str = ""
    page: int | None = None
    source_title: str = Field(
        default="",
        validation_alias=AliasChoices("source_title", "title"),
    )


def _extract_json_block(raw: str) -> str:
    for pattern in _JSON_BLOCK_PATTERNS:
        match = pattern.search(raw)
        if match:
            return match.group(1).strip()
    return "[]"


def _extract_narrative(raw: str) -> str:
    match = _NARRATIVE_PATTERN.search(raw)
    return match.group(1).strip() if match else ""


def extract_cited_articles(
    answer_text: str,
    retrieved_article_ids: set[str],
) -> tuple[list[str], list[str]]:
    valid_cited: list[str] = []
    flagged: list[str] = []
    seen: set[str] = set()

    for token in _INLINE_CITATION_PATTERN.findall(answer_text):
        article_id = token.strip()
        if not article_id or article_id in seen:
            continue
        seen.add(article_id)
        if article_id in retrieved_article_ids:
            valid_cited.append(article_id)
        else:
            flagged.append(article_id)

    return valid_cited, flagged


def validate_verdicts(
    raw_output: str,
    retrieved_article_ids: set[str],
) -> tuple[list[VerdictItem], list[str], str]:
    narrative = _extract_narrative(raw_output)
    json_block = _extract_json_block(raw_output)

    try:
        raw_items = json.loads(json_block)
    except (json.JSONDecodeError, ValueError):
        return [], ["<malformed JSON output>"], narrative

    if not isinstance(raw_items, list):
        return [], ["<malformed JSON output>"], narrative

    verdicts: list[VerdictItem] = []
    flagged: list[str] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            verdict = VerdictItem.model_validate(item)
        except ValidationError:
            continue

        if verdict.article_id and verdict.article_id not in retrieved_article_ids:
            verdict.status = "unverified"
            verdict.evidence = None
            if verdict.article_id not in flagged:
                flagged.append(verdict.article_id)

        verdicts.append(verdict)

    return verdicts, flagged, narrative

"""
Validates LLM citation output against the set of retrieved article_ids.
Any article_id not present in the retrieved set is flagged and set to "unverified".
Degrades gracefully on malformed JSON.
"""
import json
import re
from typing import Set

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class VerdictItem(BaseModel):
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
    match = re.search(
        r"##\s*JSON_VERDICTS\s*\n+```(?:json)?\s*([\s\S]+?)```",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    match = re.search(
        r"##\s*JSON_VERDICTS\s*\n+(\[[\s\S]*?\])",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    match = re.search(r"(\[[\s\S]*?\])", raw)
    if match:
        return match.group(1).strip()

    return "[]"


def _extract_narrative(raw: str) -> str:
    match = re.search(
        r"##\s*NARRATIVE_SUMMARY\s*\n+([\s\S]+?)(?:\Z|(?=##\s))",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""


def extract_cited_articles(
    answer_text: str,
    retrieved_article_ids: Set[str],
) -> tuple[list[str], list[str]]:
    tokens = re.findall(r"\[([^\[\]]+)\]", answer_text)
    seen: set[str] = set()
    valid_cited: list[str] = []
    flagged: list[str] = []

    for token in tokens:
        token = token.strip()
        if token in seen:
            continue
        seen.add(token)
        if token in retrieved_article_ids:
            valid_cited.append(token)
        else:
            flagged.append(token)
    return valid_cited, flagged


def validate_verdicts(
    raw_output: str,
    retrieved_article_ids: Set[str],
) -> tuple[list[VerdictItem], list[str], str]:
    json_str = _extract_json_block(raw_output)
    narrative = _extract_narrative(raw_output)
    flagged: list[str] = []

    try:
        raw_items = json.loads(json_str)
        if not isinstance(raw_items, list):
            raw_items = []
    except (json.JSONDecodeError, ValueError):
        return [], ["<malformed JSON output>"], narrative

    verdicts: list[VerdictItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            verdict = VerdictItem.model_validate(item)
        except Exception:
            continue

        if verdict.article_id and verdict.article_id not in retrieved_article_ids:
            verdict.status = "unverified"
            verdict.evidence = None
            if verdict.article_id not in flagged:
                flagged.append(verdict.article_id)

        verdicts.append(verdict)

    return verdicts, flagged, narrative

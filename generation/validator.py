# generation/validator.py
"""
Validates LLM citation output against the set of retrieved anchor_ids.
Any anchor_id not present in the retrieved set is flagged and set to "unverified".
Degrades gracefully on malformed JSON.
"""
import json
import re
from typing import List, Set, Tuple

from pydantic import BaseModel, field_validator


class VerdictItem(BaseModel):
    anchor_id: str = ""
    anchor_type: str = "page_only"
    section_title: str = ""
    obligation: str = ""
    status: str = "unverified"
    evidence: str | None = None
    rationale: str = ""
    page: int = 1
    title: str = ""


def _extract_json_block(raw: str) -> str:
    """Pull the JSON array from the ## JSON_VERDICTS section."""
    # Try fenced code block first
    match = re.search(
        r"##\s*JSON_VERDICTS\s*\n+```(?:json)?\s*([\s\S]+?)```",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # Try bare section (no fences)
    match = re.search(
        r"##\s*JSON_VERDICTS\s*\n+(\[[\s\S]*?\])",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # Final fallback: first JSON array in the response
    match = re.search(r"(\[[\s\S]*?\])", raw)
    if match:
        return match.group(1).strip()

    return "[]"


def _extract_narrative(raw: str) -> str:
    """Pull the narrative summary from the ## NARRATIVE_SUMMARY section."""
    match = re.search(
        r"##\s*NARRATIVE_SUMMARY\s*\n+([\s\S]+?)(?:\Z|(?=##\s))",
        raw,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""


def validate_verdicts(
    raw_output: str,
    retrieved_anchor_ids: Set[str],
) -> Tuple[List[VerdictItem], List[str], str]:
    """
    Parse and validate LLM output.

    Returns:
        verdicts      — list of VerdictItem (anchor_ids not in retrieved set → "unverified")
        flagged       — list of anchor_ids that were not in the retrieved set
        narrative     — plain-language narrative summary string
    """
    json_str = _extract_json_block(raw_output)
    narrative = _extract_narrative(raw_output)
    flagged: List[str] = []

    try:
        raw_items = json.loads(json_str)
        if not isinstance(raw_items, list):
            raw_items = []
    except (json.JSONDecodeError, ValueError):
        return [], ["<malformed JSON output>"], narrative

    verdicts: List[VerdictItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            v = VerdictItem.model_validate(item)
        except Exception:
            continue

        # Cross-check anchor_id against retrieved set
        if v.anchor_id and v.anchor_id not in retrieved_anchor_ids:
            v.status = "unverified"
            v.evidence = None
            if v.anchor_id not in flagged:
                flagged.append(v.anchor_id)

        verdicts.append(v)

    return verdicts, flagged, narrative

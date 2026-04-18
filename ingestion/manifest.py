from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ValidationError, field_validator


class SourceConfig(BaseModel):
    id: str
    title: str
    source_kind: Literal["pdf", "owl"]
    url: str
    landing_url: str | None = None
    doc_type: Literal["framework", "ontology", "consent_toolkit"]
    framework_domain: Literal["responsible_sharing", "data_use", "consent"]
    article_scheme: Literal["frs", "duo", "consent_clause"]

    @field_validator("id", "title", "url")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("landing_url")
    @classmethod
    def _normalise_landing_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def load_manifest(path: Path) -> list[SourceConfig]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    entries = raw.get("sources", []) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise ValueError(f"Manifest at {path} must be a list of source entries.")

    sources: list[SourceConfig] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Manifest entry {index} is not a mapping.")
        try:
            sources.append(SourceConfig.model_validate(entry))
        except ValidationError as exc:
            raise ValueError(f"Invalid manifest entry {index}: {exc}") from exc
    return sources

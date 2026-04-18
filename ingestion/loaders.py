from pathlib import Path

import requests

from ingestion.manifest import SourceConfig

_USER_AGENT = "GA4GH-RegBot/1.0 (+https://github.com/openai/codex)"
_EXTENSIONS = {"pdf": ".pdf", "owl": ".owl"}


def cached_path(source: SourceConfig, raw_dir: Path) -> Path:
    return raw_dir / f"{source.id}{_EXTENSIONS[source.source_kind]}"


def _looks_like_html(raw_bytes: bytes) -> bool:
    prefix = raw_bytes[:256].lstrip().lower()
    return prefix.startswith(b"<!doctype") or prefix.startswith(b"<html")


def fetch_if_missing(source: SourceConfig, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = cached_path(source, raw_dir)
    if path.exists():
        return path

    response = requests.get(
        source.url,
        headers={"User-Agent": _USER_AGENT},
        allow_redirects=True,
        timeout=30,
    )
    if response.status_code != 200:
        raise ValueError(
            f"Failed to fetch source '{source.id}' from {source.url}: "
            f"HTTP {response.status_code}"
        )

    payload = response.content
    if _looks_like_html(payload):
        raise ValueError(
            f"Fetched HTML instead of raw bytes for source '{source.id}'. "
            "Check the manifest URL and ensure it points to a direct downloadable file."
        )

    path.write_bytes(payload)
    return path

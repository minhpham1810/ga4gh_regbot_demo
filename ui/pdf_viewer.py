"""
Helpers for in-app source viewing in Streamlit.
Embeds PDFs via base64 iframe and falls back to text preview for OWL files.
"""
import base64
from pathlib import Path
from typing import Optional

import streamlit as st

from config import CORPUS_RAW_DIR


def get_cached_source_path(source_id: str, raw_dir: Path = CORPUS_RAW_DIR) -> Optional[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".pdf", ".owl"):
        candidate = raw_dir / f"{source_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def render_viewer(path: Path, page: int | None = None) -> None:
    if not path.exists():
        st.warning(f"Cached file not found: `{path.name}`")
        return

    if path.suffix.lower() == ".pdf":
        with path.open("rb") as handle:
            b64 = base64.b64encode(handle.read()).decode()
        page_fragment = f"#page={page}" if page else ""
        pdf_url = f"data:application/pdf;base64,{b64}{page_fragment}"
        st.markdown(
            f'<iframe src="{pdf_url}" width="100%" height="620px" '
            f'style="border: 1px solid #e0e0e0; border-radius: 8px;"></iframe>',
            unsafe_allow_html=True,
        )
        if page:
            st.caption(f"Page {page}")
        return

    preview = path.read_text(encoding="utf-8", errors="replace")[:4000]
    st.code(preview, language="xml")
    st.caption("OWL preview")

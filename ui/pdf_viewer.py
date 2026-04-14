# ui/pdf_viewer.py
"""
Helpers for in-app PDF viewing in Streamlit.
Embeds a PDF via base64 iframe with optional page jump.
"""
import base64
from pathlib import Path
from typing import Optional

import streamlit as st

from config import CORPUS_CACHE_DIR


def get_cached_pdf_path(drive_file_id: str, title: str) -> Optional[Path]:
    """
    Find a locally cached PDF by drive_file_id match or fuzzy title match.
    Returns None if not found.
    """
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Exact drive_file_id match in filename
    if drive_file_id:
        for f in CORPUS_CACHE_DIR.glob("*"):
            if drive_file_id in f.stem:
                return f

    # Fuzzy title match (first 15 chars of slugified title)
    title_slug = title.lower().replace(" ", "_")[:15]
    for f in CORPUS_CACHE_DIR.glob("*.pdf"):
        if title_slug[:8] in f.stem.lower():
            return f

    # Also check TXT files (corpus may be .txt)
    for f in CORPUS_CACHE_DIR.glob("*.txt"):
        if title_slug[:8] in f.stem.lower():
            return f

    return None


def render_pdf_viewer(pdf_path: Path, page: int = 1) -> None:
    """
    Embed a PDF in Streamlit using a base64-encoded data URI iframe.
    Most modern browsers support #page=N for initial page position.
    """
    if not pdf_path.exists():
        st.warning(f"Cached file not found: `{pdf_path.name}`")
        return

    if pdf_path.suffix.lower() == ".pdf":
        with open(pdf_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        pdf_url = f"data:application/pdf;base64,{b64}#page={page}"
        st.markdown(
            f'<iframe src="{pdf_url}" width="100%" height="620px" '
            f'style="border: 1px solid #e0e0e0; border-radius: 8px;"></iframe>',
            unsafe_allow_html=True,
        )
        st.caption(f"Page {page} — use the browser PDF toolbar to navigate.")
    else:
        # For TXT corpus files, render as text with line numbers
        text = pdf_path.read_text(encoding="utf-8", errors="replace")
        st.text_area(
            label=f"Source: {pdf_path.name}",
            value=text,
            height=500,
            disabled=True,
        )
        st.caption(f"Text file — cited page reference: {page}")

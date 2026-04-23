"""Minimal Streamlit UI for the GA4GH-RegBot demo."""

import sys
import tempfile
from pathlib import Path
from typing import Any

import fitz
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation.pipeline import PipelineResult, run_pipeline
from generation.validator import VerdictItem
from ui.pdf_viewer import get_cached_source_path, render_viewer

_PAGE_CSS = """
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 7rem; max-width: 1400px; }
[data-testid="stChatMessage"] { border-radius: 12px; margin-bottom: 0.5rem; }
[data-testid="stChatInput"] {
    max-width: min(980px, calc(100vw - 2rem));
    margin-left: auto;
    margin-right: auto;
}
[data-testid="stChatInput"] textarea { font-size: 1rem; }
.badge-covered { background:#d4edda; color:#155724; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.badge-partial { background:#fff3cd; color:#856404; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.badge-missing { background:#f8d7da; color:#721c24; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.badge-unverified { background:#e2e3e5; color:#383d41; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
</style>
"""
_STATE_DEFAULTS = {
    "messages": [],
    "uploaded_doc_text": "",
    "uploaded_doc_name": "",
    "source_preview_open": False,
    "source_preview_mode": None,
    "source_preview_selection": None,
}
_STATUS_CSS_CLASS = {
    "covered": "badge-covered",
    "partially covered": "badge-partial",
    "missing": "badge-missing",
    "unverified": "badge-unverified",
}
_DOMAIN_LABELS = {
    "consent": "Consent",
    "data_access": "Data Access",
    "cross_border": "Cross-Border",
    "privacy_security": "Privacy and Security",
    "general": "General",
}

st.set_page_config(page_title="GA4GH RegBot", layout="wide")
st.markdown(_PAGE_CSS, unsafe_allow_html=True)


def _init_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _conversation_history() -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in st.session_state.messages[-12:]:
        content = message.get("content", "")
        if message["role"] == "user" and "\n\n*(Document:" in content:
            content = content.split("\n\n*(Document:")[0]
        history.append({"role": message["role"], "content": content})
    return history


def _status_badge(status: str) -> str:
    css_class = _STATUS_CSS_CLASS.get(status.lower(), "badge-unverified")
    return f'<span class="{css_class}">{status}</span>'


def _format_domains(domains: list[str]) -> str:
    return " | ".join(_DOMAIN_LABELS.get(domain, domain) for domain in domains)


def _page_label(page: int | None) -> str:
    return f"p.{page}" if page is not None else "no page"


def _verdict_summary_text(verdicts: list[VerdictItem]) -> str:
    if not verdicts:
        return ""

    counts = {"covered": 0, "partially covered": 0, "missing": 0, "unverified": 0}
    for verdict in verdicts:
        counts[verdict.status.lower()] = counts.get(verdict.status.lower(), 0) + 1

    parts: list[str] = []
    if counts["covered"]:
        parts.append(f"{counts['covered']} covered")
    if counts["partially covered"]:
        parts.append(f"{counts['partially covered']} partial")
    if counts["missing"]:
        parts.append(f"{counts['missing']} missing")
    if counts["unverified"]:
        parts.append(f"{counts['unverified']} unverified")
    return " | ".join(parts)


def _unique_cited_chunks(chunks: list[Any]) -> list[Any]:
    unique_chunks: list[Any] = []
    seen: set[tuple[str, str, int | None]] = set()
    for chunk in chunks:
        key = (chunk.source_id, chunk.article_id, chunk.page)
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(chunk)
    return unique_chunks


def _open_source_preview(mode: str, selection: dict[str, Any]) -> None:
    st.session_state.source_preview_open = True
    st.session_state.source_preview_mode = mode
    st.session_state.source_preview_selection = selection


def _close_source_preview() -> None:
    st.session_state.source_preview_open = False
    st.session_state.source_preview_mode = None
    st.session_state.source_preview_selection = None


def _selection_from_chunk(chunk: Any) -> dict[str, Any]:
    return {
        "source_title": chunk.source_title,
        "page": chunk.page,
        "article_id": chunk.article_id,
        "source_id": chunk.source_id,
        "source_url": chunk.source_url,
    }


def _selection_from_verdict(verdict: VerdictItem, result: PipelineResult) -> dict[str, Any]:
    selection = {
        "source_title": verdict.source_title,
        "page": verdict.page,
        "article_id": verdict.article_id,
        "source_id": "",
        "source_url": "",
    }
    for chunk in result.retrieved_chunks:
        if chunk.article_id != verdict.article_id:
            continue
        selection["source_title"] = selection["source_title"] or chunk.source_title
        selection["page"] = selection["page"] if selection["page"] is not None else chunk.page
        selection["source_id"] = chunk.source_id
        selection["source_url"] = chunk.source_url
        break
    return selection


def _extract_uploaded_text(uploaded_file: Any) -> str:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_file.write(uploaded_file.getvalue())
            temp_path = Path(temp_file.name)
        pdf = fitz.open(str(temp_path))
        try:
            return "\n\n".join(
                page.get_text("text").strip()
                for page in pdf
                if page.get_text("text").strip()
            )
        finally:
            pdf.close()
            temp_path.unlink(missing_ok=True)
    return uploaded_file.getvalue().decode("utf-8", errors="replace")


def _attach_uploaded_document(uploaded_file: Any) -> bool:
    if uploaded_file is None:
        return False

    document_text = _extract_uploaded_text(uploaded_file)
    if document_text == st.session_state.uploaded_doc_text:
        return False

    st.session_state.uploaded_doc_text = document_text
    st.session_state.uploaded_doc_name = uploaded_file.name
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": (
                f"I've loaded **{uploaded_file.name}**. I can review it against the GA4GH "
                "corpus for consent, data-sharing, privacy/security, or cross-border issues."
            ),
            "meta": {},
        }
    )
    return True


def _submit_turn(prompt: str, uploaded_file: Any = None) -> None:
    _attach_uploaded_document(uploaded_file)
    prompt = prompt.strip()
    if not prompt:
        return

    user_content = prompt
    if st.session_state.uploaded_doc_name:
        user_content += f"\n\n*(Document: {st.session_state.uploaded_doc_name})*"
    st.session_state.messages.append({"role": "user", "content": user_content, "meta": {}})

    with st.spinner("Analysing..."):
        result = run_pipeline(
            researcher_text=st.session_state.uploaded_doc_text,
            follow_up=prompt,
            conversation_history=_conversation_history(),
        )

    reply = result.answer or result.narrative or ""
    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "meta": {"result": result}}
    )


def _render_source_preview(selection: dict[str, Any]) -> None:
    header_col, close_col = st.columns([5, 1])
    with header_col:
        st.markdown("### Source Preview")
    with close_col:
        if st.button("Close", key="close_source_preview", use_container_width=True):
            _close_source_preview()
            st.rerun()

    st.markdown(f"**{selection.get('source_title', '')}**")
    page = selection.get("page")
    article_id = selection.get("article_id", "")
    if page is None:
        st.markdown(f"Article: `{article_id}`")
    else:
        st.markdown(f"Article: `{article_id}` | Page: **{page}**")

    source_path = get_cached_source_path(selection.get("source_id", ""))
    if source_path:
        render_viewer(source_path, page=page)
    else:
        st.info("Source file not found in local raw cache.")

    if selection.get("source_url"):
        st.markdown(f"[Open original source]({selection['source_url']})")


def _render_grounded_sources(result: PipelineResult, expanded: bool) -> None:
    if not result.has_grounded_sources:
        return

    display_chunks = _unique_cited_chunks(result.cited_chunks)
    with st.expander(f"Sources ({len(display_chunks)})", expanded=expanded):
        if result.flagged_articles:
            st.warning(f"Unverified citation(s): `{'`, `'.join(result.flagged_articles)}`")

        for index, chunk in enumerate(display_chunks):
            label = chunk.section_title or chunk.article_id
            st.markdown(
                f"**{label}** - `{chunk.article_id}` | {_page_label(chunk.page)} | "
                f"*{chunk.source_title}*"
            )
            _, button_col = st.columns([5, 1])
            with button_col:
                if st.button(
                    "View Source",
                    key=f"qa_source_{index}_{chunk.source_id}_{chunk.article_id}_{chunk.page}",
                    use_container_width=True,
                ):
                    _open_source_preview("source", _selection_from_chunk(chunk))
            st.divider()


def _render_corpus_answer(result: PipelineResult) -> None:
    st.markdown(result.answer or result.narrative or "No answer was produced.")
    _render_grounded_sources(result, expanded=False)


def _render_document_review(result: PipelineResult) -> None:
    total = len(result.verdicts)
    covered = sum(verdict.status.lower() == "covered" for verdict in result.verdicts)
    needs_attention = sum(
        verdict.status.lower() in {"missing", "partially covered"}
        for verdict in result.verdicts
    )

    if result.verdicts:
        summary = (
            "I've analysed the document against the GA4GH corpus "
            f"across the **{_format_domains(result.domains)}** domain(s).\n\n"
            f"Out of **{total}** obligations checked: **{covered}** covered, "
            f"**{needs_attention}** need attention."
        )
        if result.flagged_articles:
            summary += (
                f"\n\n**{len(result.flagged_articles)}** citation(s) could not be verified "
                "and were marked as *unverified*."
            )
    else:
        summary = (
            f"I analysed the document in the **{_format_domains(result.domains)}** domain(s), "
            "but no structured verdicts were produced. See the narrative below."
        )

    st.markdown(summary)

    if result.domains:
        left_col, right_col = st.columns([3, 2])
        with left_col:
            st.caption(f"Domains: {_format_domains(result.domains)}")
        with right_col:
            st.caption(_verdict_summary_text(result.verdicts))

    if result.narrative:
        with st.expander("Detailed analysis", expanded=False):
            st.markdown(result.narrative)

    if not result.verdicts:
        return

    with st.expander(f"Evidence and citations ({len(result.verdicts)} items)", expanded=False):
        if result.flagged_articles:
            st.warning(f"Unverified: `{'`, `'.join(result.flagged_articles)}`")

        for index, verdict in enumerate(result.verdicts):
            st.markdown(
                f"{_status_badge(verdict.status)} &nbsp; "
                f"**{verdict.section_title or verdict.article_id}** - `{verdict.article_id}`",
                unsafe_allow_html=True,
            )
            if verdict.obligation:
                st.markdown(f"*Obligation:* {verdict.obligation}")
            if verdict.evidence:
                clipped = verdict.evidence[:300]
                suffix = "..." if len(verdict.evidence) > 300 else ""
                st.markdown(f"> {clipped}{suffix}")
            if verdict.rationale:
                st.caption(verdict.rationale)

            _, button_col = st.columns([4, 1])
            with button_col:
                if st.button(
                    "View Source",
                    key=f"review_source_{index}_{verdict.article_id}_{verdict.page}",
                    use_container_width=True,
                ):
                    _open_source_preview("review_detail", _selection_from_verdict(verdict, result))
            st.divider()


def _render_result(result: PipelineResult) -> None:
    route_intent = getattr(result, "route_intent", "")
    off_topic = getattr(result, "off_topic", False)
    is_document_review = getattr(
        result,
        "is_document_review",
        getattr(result, "chat_mode", "corpus_qa") == "document_review",
    )

    if result.error:
        st.markdown(result.answer or result.narrative)
        return
    if route_intent in {"small_talk", "off_topic_redirect", "clarify"} or off_topic:
        st.markdown(result.answer or result.narrative)
        return
    if is_document_review:
        _render_document_review(result)
        return
    _render_corpus_answer(result)


def _render_message(message: dict[str, Any]) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(message["content"])
            return

        result = message.get("meta", {}).get("result")
        if result:
            _render_result(result)
        else:
            st.markdown(message.get("content", ""))


def _render_header() -> None:
    st.markdown("## GA4GH RegBot")
    st.caption("Evidence-backed GA4GH guidance for standards questions and document review.")


def _render_chat_history() -> None:
    for message in st.session_state.messages:
        _render_message(message)


def _render_chat_input() -> None:
    chat_value = st.chat_input(
        "Ask about GA4GH guidance, or upload a document for review...",
        accept_file=True,
        file_type=["pdf", "txt"],
    )
    if not chat_value:
        return

    if isinstance(chat_value, str):
        _submit_turn(chat_value)
        st.rerun()
        return

    uploaded_file = chat_value.files[0] if chat_value.files else None
    _submit_turn(chat_value.text, uploaded_file=uploaded_file)
    st.rerun()


def _render_workspace() -> None:
    _render_header()
    _render_chat_history()


_init_state()

preview_open = (
    st.session_state.source_preview_open
    and st.session_state.source_preview_selection is not None
)
if preview_open:
    chat_col, preview_col = st.columns([2, 1.1], gap="large")
else:
    chat_col = st.container()
    preview_col = None

with chat_col:
    _render_workspace()

if preview_col is not None:
    with preview_col:
        with st.container(border=True):
            _render_source_preview(st.session_state.source_preview_selection)

_render_chat_input()

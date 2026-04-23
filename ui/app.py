"""
GA4GH RegBot - Chat-first Streamlit UI.
Run with: streamlit run ui/app.py
"""
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import fitz
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation.pipeline import PipelineResult, run_pipeline
from generation.validator import VerdictItem
from ui.pdf_viewer import get_cached_source_path, render_viewer

st.set_page_config(
    page_title="GA4GH RegBot",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 7rem; max-width: 1400px; }
    [data-testid="stChatMessage"] { border-radius: 12px; margin-bottom: 0.5rem; }
    [data-testid="stChatInput"] {
        max-width: min(980px, calc(100vw - 2rem));
        margin-left: auto;
        margin-right: auto;
    }
    [data-testid="stChatInput"] textarea {
        font-size: 1rem;
    }
    .badge-covered     { background:#d4edda; color:#155724; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-partial     { background:#fff3cd; color:#856404; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-missing     { background:#f8d7da; color:#721c24; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-unverified  { background:#e2e3e5; color:#383d41; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state() -> None:
    defaults = {
        "messages": [],
        "uploaded_doc_text": "",
        "uploaded_doc_name": "",
        "last_result": None,
        "rail_open": False,
        "rail_mode": None,
        "rail_selection": None,
        "rail_available": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _status_badge(status: str) -> str:
    css_class = {
        "covered": "badge-covered",
        "partially covered": "badge-partial",
        "missing": "badge-missing",
        "unverified": "badge-unverified",
    }.get(status.lower(), "badge-unverified")
    return f'<span class="{css_class}">{status}</span>'


def _format_domains(domains: list[str]) -> str:
    labels = {
        "consent": "Consent",
        "data_access": "Data Access",
        "cross_border": "Cross-Border",
        "privacy_security": "Privacy and Security",
        "general": "General",
    }
    return " | ".join(labels.get(domain, domain) for domain in domains)


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


def _get_history() -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for msg in st.session_state.messages[-12:]:
        role = msg["role"]
        content = msg.get("content", "")
        if role == "user" and "\n\n*(Document:" in content:
            content = content.split("\n\n*(Document:")[0]
        history.append({"role": role, "content": content})
    return history


def _page_label(page: int | None) -> str:
    return f"p.{page}" if page is not None else "no page"


def _unique_cited_chunks(chunks: list) -> list:
    unique_chunks: list = []
    seen: set[tuple[str, str, int | None]] = set()

    for chunk in chunks:
        key = (chunk.source_id, chunk.article_id, chunk.page)
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(chunk)

    return unique_chunks


def _set_rail_available(available: bool) -> None:
    st.session_state.rail_available = available
    if not available and not st.session_state.rail_open:
        st.session_state.rail_mode = None
        st.session_state.rail_selection = None


def _open_context_rail(mode: str, selection: dict[str, Any]) -> None:
    st.session_state.rail_open = True
    st.session_state.rail_mode = mode
    st.session_state.rail_selection = selection
    _set_rail_available(True)


def _close_context_rail() -> None:
    st.session_state.rail_open = False
    st.session_state.rail_mode = None
    st.session_state.rail_selection = None


def _rail_selection_from_chunk(chunk) -> dict[str, Any]:
    return {
        "kind": "source",
        "source_title": chunk.source_title,
        "page": chunk.page,
        "article_id": chunk.article_id,
        "source_id": chunk.source_id,
        "source_url": chunk.source_url,
    }


def _rail_selection_from_verdict(verdict: VerdictItem, result: PipelineResult) -> dict[str, Any]:
    selection = {
        "kind": "source",
        "source_title": verdict.source_title,
        "page": verdict.page,
        "article_id": verdict.article_id,
        "source_id": "",
        "source_url": "",
    }
    for chunk in result.retrieved_chunks:
        if chunk.article_id != verdict.article_id:
            continue
        selection["source_url"] = chunk.source_url
        selection["source_id"] = chunk.source_id
        if selection["page"] is None:
            selection["page"] = chunk.page
        if not selection["source_title"]:
            selection["source_title"] = chunk.source_title
        break
    return selection


def _extract_uploaded_text(uploaded_file) -> str:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = Path(tmp.name)
        pdf = fitz.open(str(tmp_path))
        try:
            return "\n\n".join(
                page.get_text("text").strip()
                for page in pdf
                if page.get_text("text").strip()
            )
        finally:
            pdf.close()
            tmp_path.unlink(missing_ok=True)
    return uploaded_file.getvalue().decode("utf-8", errors="replace")


def _attach_uploaded_document(uploaded_file) -> bool:
    if uploaded_file is None:
        return False

    doc_text = _extract_uploaded_text(uploaded_file)
    if doc_text == st.session_state.uploaded_doc_text:
        return False

    st.session_state.uploaded_doc_text = doc_text
    st.session_state.uploaded_doc_name = uploaded_file.name
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": (
                f"I've loaded **{uploaded_file.name}**. I can analyze it for consent, "
                "data-sharing, privacy/security, or cross-border transfer issues. "
                "Try asking *'What are the biggest gaps?'* or "
                "*'Does this address secondary use?'*"
            ),
            "meta": {},
        }
    )
    return True


def _push_message(prompt: str, uploaded_file=None) -> None:
    attached = _attach_uploaded_document(uploaded_file)
    prompt = prompt.strip()
    if not prompt:
        if attached:
            return
        return

    user_content = prompt
    if st.session_state.uploaded_doc_name:
        user_content += f"\n\n*(Document: {st.session_state.uploaded_doc_name})*"
    st.session_state.messages.append({"role": "user", "content": user_content, "meta": {}})

    with st.spinner("Analysing..."):
        result = run_pipeline(
            researcher_text=st.session_state.uploaded_doc_text,
            follow_up=prompt,
            conversation_history=_get_history(),
        )

    reply = result.answer or result.narrative or ""
    st.session_state.last_result = result
    _set_rail_available(result.can_open_context_rail)

    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "meta": {"result": result}}
    )


def _render_source_panel(selection: dict[str, Any]) -> None:
    source_title = selection.get("source_title", "")
    article_id = selection.get("article_id", "")
    page = selection.get("page")

    header_col, close_col = st.columns([5, 1])
    with header_col:
        st.markdown("### Source Preview")
    with close_col:
        if st.button("Close", key="close_context_rail", use_container_width=True):
            _close_context_rail()
            st.rerun()

    st.markdown(f"**{source_title}**")
    if page is not None:
        st.markdown(f"Article: `{article_id}`  |  Page: **{page}**")
    else:
        st.markdown(f"Article: `{article_id}`")

    source_path = get_cached_source_path(selection.get("source_id", ""))
    if source_path:
        render_viewer(source_path, page=page)
    else:
        st.info("Source file not found in local raw cache.")

    if selection.get("source_url"):
        st.markdown(f"[Open original source]({selection['source_url']})")


def _render_context_rail() -> None:
    selection = st.session_state.rail_selection
    if not selection:
        return

    with st.container(border=True):
        mode = st.session_state.rail_mode
        if mode in {"source", "review_detail"}:
            _render_source_panel(selection)
        else:
            st.info("No context selected.")


def _render_grounded_sources(result: PipelineResult, live: bool) -> None:
    if not result.has_grounded_sources:
        return

    display_chunks = _unique_cited_chunks(result.cited_chunks)
    with st.expander(f"Sources ({len(display_chunks)})", expanded=live):
        if result.flagged_articles:
            st.warning(f"Unverified citation(s): `{'`, `'.join(result.flagged_articles)}`")
        for index, chunk in enumerate(display_chunks):
            label = chunk.section_title or chunk.article_id
            st.markdown(
                f"**{label}** - `{chunk.article_id}` | {_page_label(chunk.page)} | "
                f"*{chunk.source_title}*"
            )
            columns = st.columns([5, 1])
            with columns[1]:
                if st.button(
                    "View Source",
                    key=(
                        f"qa_src_{index}_{chunk.source_id}_{chunk.article_id}_"
                        f"{chunk.page}_{id(result)}"
                    ),
                    use_container_width=True,
                ):
                    _open_context_rail("source", _rail_selection_from_chunk(chunk))
            st.divider()


def _render_corpus_qa(result: PipelineResult, live: bool = False) -> str:
    reply = result.answer or result.narrative or "No answer was produced."
    st.markdown(reply)
    _render_grounded_sources(result, live=live)
    return reply


def _render_document_review(result: PipelineResult, live: bool = False) -> str:
    n_issues = sum(
        1
        for verdict in result.verdicts
        if verdict.status.lower() in {"missing", "partially covered"}
    )
    n_covered = sum(1 for verdict in result.verdicts if verdict.status.lower() == "covered")
    domains_str = _format_domains(result.domains)

    if result.verdicts:
        reply = (
            "I've analysed the document against the GA4GH corpus "
            f"across the **{domains_str}** domain(s).\n\n"
            f"Out of **{len(result.verdicts)}** obligations checked: "
            f"**{n_covered}** covered, **{n_issues}** need attention."
        )
        if result.flagged_articles:
            reply += (
                f"\n\n**{len(result.flagged_articles)}** citation(s) could not be verified "
                "and were marked as *unverified*."
            )
    else:
        reply = (
            f"I analysed the document in the **{domains_str}** domain(s), "
            "but no structured verdicts were produced. See the narrative below."
        )

    st.markdown(reply)

    if result.domains:
        columns = st.columns([3, 2])
        with columns[0]:
            st.caption(f"Domains: {_format_domains(result.domains)}")
        with columns[1]:
            st.caption(_verdict_summary_text(result.verdicts))

    if result.narrative:
        with st.expander("Detailed analysis", expanded=False):
            st.markdown(result.narrative)

    if result.verdicts:
        with st.expander(f"Evidence and citations ({len(result.verdicts)} items)", expanded=live):
            if result.flagged_articles:
                st.warning(f"Unverified: `{'`, `'.join(result.flagged_articles)}`")
            for index, verdict in enumerate(result.verdicts):
                badge_html = _status_badge(verdict.status)
                st.markdown(
                    f"{badge_html} &nbsp; **{verdict.section_title or verdict.article_id}** "
                    f"- `{verdict.article_id}`",
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
                columns = st.columns([4, 1])
                with columns[1]:
                    if st.button(
                        "View Source",
                        key=f"dr_src_{index}_{verdict.article_id}_{verdict.page}_{id(result)}",
                        use_container_width=True,
                    ):
                        _open_context_rail(
                            "review_detail",
                            _rail_selection_from_verdict(verdict, result),
                        )
                st.divider()

    return reply


def _render_result(result: PipelineResult, live: bool = False) -> str:
    route_intent = getattr(result, "route_intent", "")
    off_topic = getattr(result, "off_topic", False)
    is_document_review = getattr(
        result,
        "is_document_review",
        getattr(result, "chat_mode", "corpus_qa") == "document_review",
    )

    if result.error:
        reply = result.answer or result.narrative
        st.markdown(reply)
        return reply
    if route_intent in {"small_talk", "off_topic_redirect", "clarify"} or off_topic:
        reply = result.answer or result.narrative
        st.markdown(reply)
        return reply
    if not result.retrieved_chunks and not result.answer:
        reply = (
            "I couldn't find any relevant GA4GH policy passages. "
            "Please index the corpus first."
        )
        st.markdown(reply)
        return reply
    if is_document_review:
        return _render_document_review(result, live=live)
    return _render_corpus_qa(result, live=live)


def _render_message(message: dict[str, Any]) -> None:
    role = message["role"]
    with st.chat_message(role):
        if role == "user":
            st.markdown(message["content"])
            return

        result: Optional[PipelineResult] = message.get("meta", {}).get("result")
        if result:
            _render_result(result, live=False)
        else:
            st.markdown(message.get("content", ""))


def _render_chat_header() -> None:
    st.markdown("## GA4GH RegBot")
    st.caption(
        "Evidence-backed GA4GH guidance for standards questions and document review."
    )


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
        _push_message(chat_value)
        st.rerun()
        return

    uploaded_file = chat_value.files[0] if chat_value.files else None
    _push_message(chat_value.text, uploaded_file=uploaded_file)
    st.rerun()


def _render_chat_workspace() -> None:
    _render_chat_header()
    _render_chat_history()


_init_state()

has_rail = st.session_state.rail_open and st.session_state.rail_selection is not None
if has_rail:
    chat_col, preview_col = st.columns([2, 1.1], gap="large")
else:
    chat_col = st.container()
    preview_col = None

with chat_col:
    _render_chat_workspace()

if preview_col is not None:
    with preview_col:
        _render_context_rail()

_render_chat_input()

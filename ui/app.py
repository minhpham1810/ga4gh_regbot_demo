"""
GA4GH RegBot - Chat-first Streamlit UI.
Run with: streamlit run ui/app.py
"""
import sys
import tempfile
from pathlib import Path
from typing import Optional

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
    .block-container { padding-top: 1.5rem; padding-bottom: 0; max-width: 1400px; }
    [data-testid="stChatMessage"] { border-radius: 12px; margin-bottom: 0.5rem; }
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
        "source_preview": None,
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


def _get_history() -> list[dict]:
    history: list[dict] = []
    for msg in st.session_state.messages[-12:]:
        role = msg["role"]
        content = msg.get("content", "")
        if role == "user" and "\n\n*(Document:" in content:
            content = content.split("\n\n*(Document:")[0]
        history.append({"role": role, "content": content})
    return history


def _push_message(prompt: str) -> None:
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
    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "meta": {"result": result}}
    )


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


def _set_source_preview(preview: dict) -> None:
    st.session_state.source_preview = preview


def _source_preview_from_chunk(chunk) -> dict:
    return {
        "source_title": chunk.source_title,
        "page": chunk.page,
        "article_id": chunk.article_id,
        "source_id": chunk.source_id,
        "source_url": chunk.source_url,
    }


def _source_preview_from_verdict(verdict: VerdictItem, result: PipelineResult) -> dict:
    preview = {
        "source_title": verdict.source_title,
        "page": verdict.page,
        "article_id": verdict.article_id,
        "source_id": "",
        "source_url": "",
    }
    for chunk in result.retrieved_chunks:
        if chunk.article_id == verdict.article_id:
            preview["source_url"] = chunk.source_url
            preview["source_id"] = chunk.source_id
            if preview["page"] is None:
                preview["page"] = chunk.page
            if not preview["source_title"]:
                preview["source_title"] = chunk.source_title
            break
    return preview


def _render_source_preview_panel() -> None:
    sp = st.session_state.source_preview
    source_title = sp.get("source_title", "")
    article_id = sp.get("article_id", "")
    page = sp.get("page")

    header_col, close_col = st.columns([5, 1])
    with header_col:
        st.markdown("### Source Preview")
    with close_col:
        if st.button("Close", key="close_source_preview", use_container_width=True):
            st.session_state.source_preview = None
            st.rerun()

    st.markdown(f"**{source_title}**")
    if page is not None:
        st.markdown(f"Article: `{article_id}`  |  Page: **{page}**")
    else:
        st.markdown(f"Article: `{article_id}`")

    source_path = get_cached_source_path(sp.get("source_id", ""))
    if source_path:
        render_viewer(source_path, page=page)
    else:
        st.info("Source file not found in local raw cache.")

    if sp.get("source_url"):
        st.markdown(f"[Open original source]({sp['source_url']})")


def _render_corpus_qa(result: PipelineResult, live: bool = False) -> str:
    reply = result.answer or result.narrative or "No answer was produced."
    st.markdown(reply)

    if result.cited_chunks:
        display_chunks = _unique_cited_chunks(result.cited_chunks)
        with st.expander(f"Sources ({len(display_chunks)})", expanded=live):
            if result.flagged_articles:
                st.warning(
                    f"Unverified citation(s): `{'`, `'.join(result.flagged_articles)}`"
                )
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
                        _set_source_preview(_source_preview_from_chunk(chunk))
                st.divider()
    return reply


def _render_document_review(result: PipelineResult, live: bool = False) -> str:
    if result.error:
        reply = f"Something went wrong:\n\n> {result.error}"
        st.markdown(reply)
        return reply

    n_issues = sum(
        1 for verdict in result.verdicts if verdict.status.lower() in {"missing", "partially covered"}
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
                        _set_source_preview(_source_preview_from_verdict(verdict, result))
                st.divider()

    return reply


def _render_result(result: PipelineResult, live: bool = False) -> str:
    if result.off_topic:
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
    if result.chat_mode == "corpus_qa":
        return _render_corpus_qa(result, live=live)
    return _render_document_review(result, live=live)


_init_state()

has_preview = st.session_state.source_preview is not None
if has_preview:
    chat_col, preview_col = st.columns([2, 1.1], gap="large")
else:
    chat_col = st.container()
    preview_col = None

with chat_col:
    st.markdown("## GA4GH RegBot")
    st.caption("Ask about GA4GH standards, or upload a document for a compliance gap analysis.")

    uploaded_file = st.file_uploader(
        "Upload researcher document (PDF or TXT)",
        type=["pdf", "txt"],
        label_visibility="collapsed",
        key="file_uploader",
    )

    if uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix == ".pdf":
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = Path(tmp.name)
            pdf = fitz.open(str(tmp_path))
            try:
                doc_text = "\n\n".join(
                    page.get_text("text").strip()
                    for page in pdf
                    if page.get_text("text").strip()
                )
            finally:
                pdf.close()
                tmp_path.unlink(missing_ok=True)
        else:
            doc_text = uploaded_file.getvalue().decode("utf-8", errors="replace")

        if doc_text != st.session_state.uploaded_doc_text:
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

    for msg in st.session_state.messages:
        role = msg["role"]
        with st.chat_message(role):
            if role == "user":
                st.markdown(msg["content"])
            else:
                result: Optional[PipelineResult] = msg.get("meta", {}).get("result")
                if result:
                    _render_result(result, live=False)
                else:
                    st.markdown(msg.get("content", ""))
    if prompt := st.chat_input("Ask about GA4GH guidance, or upload a document for review..."):
        _push_message(prompt)
        st.rerun()

if preview_col is not None:
    with preview_col:
        with st.container(border=True):
            _render_source_preview_panel()

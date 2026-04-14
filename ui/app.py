# ui/app.py
"""
GA4GH RegBot — Chat-first Streamlit UI.
Run with: streamlit run ui/app.py
"""
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from typing import Optional

import streamlit as st

from config import CORPUS_DIR, CHROMA_DIR, CORPUS_COLLECTION
from generation.pipeline import run_pipeline, PipelineResult
from generation.validator import VerdictItem
from ui.pdf_viewer import get_cached_pdf_path, render_pdf_viewer

# ─── Page config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GA4GH RegBot",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    /* Main container spacing */
    .block-container { padding-top: 1.5rem; padding-bottom: 0; max-width: 900px; }

    /* Chat bubbles */
    [data-testid="stChatMessage"] { border-radius: 12px; margin-bottom: 0.5rem; }

    /* Status badge colours */
    .badge-covered     { background:#d4edda; color:#155724; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-partial     { background:#fff3cd; color:#856404; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-missing     { background:#f8d7da; color:#721c24; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-unverified  { background:#e2e3e5; color:#383d41; padding:2px 8px;
                         border-radius:4px; font-size:0.78rem; font-weight:600; }

    /* Source preview panel */
    .source-panel { background:#f8f9fa; border-radius:10px; padding:1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Session state initialisation ───────────────────────────────────────────

def _init_state():
    defaults = {
        "messages": [],          # list of {"role": "user"|"assistant", "content": ..., "meta": ...}
        "uploaded_doc_text": "", # full text of current uploaded document
        "uploaded_doc_name": "", # filename
        "last_result": None,     # PipelineResult from last analysis
        "source_preview": None,  # {"title", "page", "anchor_id", "drive_file_id"}
        "corpus_ingested": None, # True/False/None (unknown)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ─── Helpers ────────────────────────────────────────────────────────────────

def _status_badge(status: str) -> str:
    css_class = {
        "covered": "badge-covered",
        "partially covered": "badge-partial",
        "missing": "badge-missing",
        "unverified": "badge-unverified",
    }.get(status.lower(), "badge-unverified")
    return f'<span class="{css_class}">{status}</span>'


def _corpus_is_ingested() -> bool:
    """Quick check — does the ChromaDB collection have any documents?"""
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        from config import EMBEDDING_MODEL

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        col = client.get_or_create_collection(
            CORPUS_COLLECTION, embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        return col.count() > 0
    except Exception:
        return False


def _ingest_corpus():
    """Run corpus ingestion and cache the result."""
    from ingestion.ingest import ingest_corpus
    with st.spinner("Ingesting GA4GH corpus into ChromaDB…"):
        total = ingest_corpus(CORPUS_DIR)
    st.session_state.corpus_ingested = total > 0
    return total


def _format_domains(domains: list[str]) -> str:
    labels = {
        "consent": "Consent",
        "data_access": "Data Access",
        "cross_border": "Cross-Border",
        "privacy_security": "Privacy & Security",
        "general": "General",
    }
    return " · ".join(labels.get(d, d) for d in domains)


def _verdict_summary_text(verdicts: list[VerdictItem]) -> str:
    if not verdicts:
        return "No structured verdicts were produced."
    counts = {"covered": 0, "partially covered": 0, "missing": 0, "unverified": 0}
    for v in verdicts:
        key = v.status.lower()
        if key in counts:
            counts[key] += 1
        else:
            counts["unverified"] += 1
    parts = []
    if counts["covered"]:
        parts.append(f"✅ {counts['covered']} covered")
    if counts["partially covered"]:
        parts.append(f"⚠️ {counts['partially covered']} partially covered")
    if counts["missing"]:
        parts.append(f"❌ {counts['missing']} missing")
    if counts["unverified"]:
        parts.append(f"🔘 {counts['unverified']} unverified")
    return "  |  ".join(parts)


# ─── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🧬 GA4GH RegBot")
    st.caption("Local-first compliance assistant")
    st.divider()

    # Corpus status
    if st.session_state.corpus_ingested is None:
        st.session_state.corpus_ingested = _corpus_is_ingested()

    if st.session_state.corpus_ingested:
        st.success("Corpus ready", icon="✅")
    else:
        st.warning("Corpus not ingested", icon="⚠️")

    if st.button("Ingest sample corpus", use_container_width=True):
        total = _ingest_corpus()
        if total > 0:
            st.success(f"Ingested {total} chunks")
        else:
            st.error("No files found in corpus directory.")

    st.divider()
    st.markdown("**Corpus directory**")
    st.code(str(CORPUS_DIR), language=None)

    st.divider()

    # Source preview panel
    if st.session_state.source_preview:
        sp = st.session_state.source_preview
        st.markdown("#### 📄 Source Preview")
        st.markdown(f"**{sp['title']}**")
        st.markdown(f"Anchor: `{sp['anchor_id']}`  |  Page: **{sp['page']}**")

        pdf_path = get_cached_pdf_path(sp.get("drive_file_id", ""), sp["title"])
        if pdf_path:
            render_pdf_viewer(pdf_path, page=sp["page"])
        else:
            st.info("Source file not found in local cache.")

        if sp.get("source_url"):
            st.markdown(f"[Open original source]({sp['source_url']})")

        if st.button("Close preview", use_container_width=True):
            st.session_state.source_preview = None
            st.rerun()

# ─── Main chat area ─────────────────────────────────────────────────────────

st.markdown("## 🧬 GA4GH RegBot")
st.caption(
    "Upload a data use letter, consent form, or related document "
    "to get a compliance gap analysis grounded in GA4GH standards."
)

# File uploader (above chat input, below title)
uploaded_file = st.file_uploader(
    "Upload researcher document (PDF or TXT)",
    type=["pdf", "txt"],
    label_visibility="collapsed",
    key="file_uploader",
)

if uploaded_file is not None:
    # Parse and store uploaded document
    import fitz

    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = Path(tmp.name)
        doc = fitz.open(str(tmp_path))
        doc_text = "\n\n".join(
            page.get_text("text") for page in doc if page.get_text("text").strip()
        )
        doc.close()
        tmp_path.unlink(missing_ok=True)
    else:
        doc_text = uploaded_file.getvalue().decode("utf-8", errors="replace")

    if doc_text != st.session_state.uploaded_doc_text:
        st.session_state.uploaded_doc_text = doc_text
        st.session_state.uploaded_doc_name = uploaded_file.name
        # Add a system-style user message to chat
        st.session_state.messages.append({
            "role": "user",
            "content": f"I've uploaded **{uploaded_file.name}** for compliance review.",
            "meta": {"file": uploaded_file.name},
        })

# ─── Render chat history ─────────────────────────────────────────────────────

for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role, avatar="🧬" if role == "assistant" else None):
        # User messages
        if role == "user":
            st.markdown(msg["content"])

        # Assistant messages
        elif role == "assistant":
            content = msg.get("content", "")
            result: Optional[PipelineResult] = msg.get("meta", {}).get("result")

            st.markdown(content)

            if result and not result.off_topic:
                # Compact verdict summary line
                if result.verdicts or result.domains:
                    cols = st.columns([3, 2])
                    with cols[0]:
                        st.caption(f"Domains: {_format_domains(result.domains)}")
                    with cols[1]:
                        st.caption(_verdict_summary_text(result.verdicts))

                # Narrative
                if result.narrative:
                    with st.expander("📝 Detailed analysis", expanded=False):
                        st.markdown(result.narrative)

                # Evidence / citations
                if result.verdicts:
                    with st.expander(
                        f"🔍 Evidence & citations ({len(result.verdicts)} items)",
                        expanded=False,
                    ):
                        if result.flagged_anchors:
                            st.warning(
                                f"⚠️ {len(result.flagged_anchors)} citation(s) could not be "
                                f"verified against retrieved sources: "
                                f"`{'`, `'.join(result.flagged_anchors)}`"
                            )

                        for v in result.verdicts:
                            badge_html = _status_badge(v.status)
                            st.markdown(
                                f"{badge_html} &nbsp; **{v.section_title or v.anchor_id}** "
                                f"— `{v.anchor_id}`",
                                unsafe_allow_html=True,
                            )
                            if v.obligation:
                                st.markdown(f"*Obligation:* {v.obligation}")
                            if v.evidence:
                                st.markdown(
                                    f"> {v.evidence[:300]}{'…' if len(v.evidence) > 300 else ''}"
                                )
                            if v.rationale:
                                st.caption(v.rationale)

                            source_cols = st.columns([4, 1])
                            with source_cols[1]:
                                if st.button(
                                    "View Source",
                                    key=f"src_{v.anchor_id}_{id(msg)}",
                                    use_container_width=True,
                                ):
                                    st.session_state.source_preview = {
                                        "title": v.title,
                                        "page": v.page,
                                        "anchor_id": v.anchor_id,
                                        "drive_file_id": "",
                                        "source_url": "",
                                    }
                                    # Find source_url from retrieved chunks
                                    if result.retrieved_chunks:
                                        for chunk in result.retrieved_chunks:
                                            if chunk.anchor_id == v.anchor_id:
                                                st.session_state.source_preview["source_url"] = chunk.source_url
                                                st.session_state.source_preview["drive_file_id"] = chunk.drive_file_id
                                                break
                                    st.rerun()
                            st.divider()

# ─── Chat input ──────────────────────────────────────────────────────────────

chat_placeholder = (
    "Ask a compliance question, or type 'analyze' after uploading a document…"
    if st.session_state.uploaded_doc_name
    else "Upload a document above, then ask your compliance question…"
)

if prompt := st.chat_input(chat_placeholder):
    # Show user message
    user_msg = {"role": "user", "content": prompt, "meta": {}}
    if st.session_state.uploaded_doc_name:
        user_msg["content"] = (
            f"{prompt}\n\n*(Document: {st.session_state.uploaded_doc_name})*"
        )
    st.session_state.messages.append(user_msg)

    with st.chat_message("user"):
        st.markdown(user_msg["content"])

    # Run analysis
    with st.chat_message("assistant", avatar="🧬"):
        with st.spinner("Analysing…"):
            result = run_pipeline(
                researcher_text=st.session_state.uploaded_doc_text,
                follow_up=prompt,
            )

        # Build a conversational opening paragraph
        if result.off_topic:
            reply = result.narrative
        elif result.error:
            reply = f"Something went wrong during analysis:\n\n> {result.error}"
        elif not result.retrieved_chunks:
            reply = (
                "I couldn't find any relevant GA4GH policy passages. "
                "Please make sure the corpus has been ingested using the sidebar button."
            )
        else:
            n_issues = sum(
                1 for v in result.verdicts
                if v.status.lower() in ("missing", "partially covered")
            )
            n_covered = sum(
                1 for v in result.verdicts if v.status.lower() == "covered"
            )
            domains_str = _format_domains(result.domains)

            if result.verdicts:
                reply = (
                    f"I've analysed the document against the GA4GH corpus "
                    f"across the **{domains_str}** domain(s).\n\n"
                    f"Out of **{len(result.verdicts)}** obligations checked: "
                    f"**{n_covered}** are covered, "
                    f"**{n_issues}** need attention (missing or partially covered)."
                )
                if result.flagged_anchors:
                    reply += (
                        f"\n\n⚠️ **{len(result.flagged_anchors)}** citation(s) could not "
                        f"be verified against the retrieved evidence and have been marked "
                        f"as *unverified*."
                    )
            else:
                reply = (
                    f"I analysed the document in the **{domains_str}** domain(s), "
                    "but the model did not produce structured verdicts. "
                    "See the narrative summary below for details."
                )

        st.markdown(reply)

        if result and not result.off_topic:
            if result.domains:
                cols = st.columns([3, 2])
                with cols[0]:
                    st.caption(f"Domains: {_format_domains(result.domains)}")
                with cols[1]:
                    st.caption(_verdict_summary_text(result.verdicts))

            if result.narrative:
                with st.expander("📝 Detailed analysis", expanded=False):
                    st.markdown(result.narrative)

            if result.verdicts:
                with st.expander(
                    f"🔍 Evidence & citations ({len(result.verdicts)} items)",
                    expanded=True,
                ):
                    if result.flagged_anchors:
                        st.warning(
                            f"⚠️ Unverified citations: "
                            f"`{'`, `'.join(result.flagged_anchors)}`"
                        )

                    for v in result.verdicts:
                        badge_html = _status_badge(v.status)
                        st.markdown(
                            f"{badge_html} &nbsp; **{v.section_title or v.anchor_id}** "
                            f"— `{v.anchor_id}`",
                            unsafe_allow_html=True,
                        )
                        if v.obligation:
                            st.markdown(f"*Obligation:* {v.obligation}")
                        if v.evidence:
                            st.markdown(
                                f"> {v.evidence[:300]}{'…' if len(v.evidence) > 300 else ''}"
                            )
                        if v.rationale:
                            st.caption(v.rationale)

                        s_cols = st.columns([4, 1])
                        with s_cols[1]:
                            if st.button(
                                "View Source",
                                key=f"src_new_{v.anchor_id}_{id(result)}",
                                use_container_width=True,
                            ):
                                st.session_state.source_preview = {
                                    "title": v.title,
                                    "page": v.page,
                                    "anchor_id": v.anchor_id,
                                    "drive_file_id": "",
                                    "source_url": "",
                                }
                                for chunk in result.retrieved_chunks:
                                    if chunk.anchor_id == v.anchor_id:
                                        st.session_state.source_preview["source_url"] = chunk.source_url
                                        st.session_state.source_preview["drive_file_id"] = chunk.drive_file_id
                                        break
                                st.rerun()
                        st.divider()

        st.session_state.last_result = result

    # Save assistant message to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": reply,
        "meta": {"result": result},
    })

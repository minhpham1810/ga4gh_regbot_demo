"""
End-to-end compliance analysis pipeline for a single turn.

Two modes:
  corpus_qa       - no uploaded document; conversational Q&A from corpus
  document_review - uploaded document present; full compliance verdict analysis
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import fitz

from config import TOP_K
from generation.gap_detector import answer_corpus_question, detect_gaps
from generation.validator import VerdictItem, extract_cited_articles, validate_verdicts
from retrieval.classifier import classify_domains
from retrieval.retriever import RetrievedChunk, retrieve

_OFF_TOPIC_SIGNALS = [
    "weather",
    "stock price",
    "stock market",
    "recipe",
    "sports",
    "joke",
    "movie",
    "translate this",
    "who is the president",
    "capital of",
    "how to cook",
]

_COMPLIANCE_SIGNALS = [
    "consent",
    "data",
    "compliance",
    "access",
    "privacy",
    "gdpr",
    "research",
    "ethics",
    "genomic",
    "sharing",
    "duo",
    "dul",
    "ga4gh",
    "framework",
    "policy",
    "clause",
    "agreement",
]


def _is_off_topic(text: str) -> bool:
    lower = text.lower()
    has_off_topic = any(signal in lower for signal in _OFF_TOPIC_SIGNALS)
    has_compliance = any(signal in lower for signal in _COMPLIANCE_SIGNALS)
    return has_off_topic and not has_compliance


@dataclass
class PipelineResult:
    chat_mode: str = "corpus_qa"
    domains: list[str] = field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    verdicts: list[VerdictItem] = field(default_factory=list)
    flagged_articles: list[str] = field(default_factory=list)
    narrative: str = ""
    answer: str = ""
    cited_chunks: list[RetrievedChunk] = field(default_factory=list)
    off_topic: bool = False
    error: Optional[str] = None


_OFF_TOPIC_RESPONSE = (
    "I'm a GA4GH compliance assistant. I can answer questions about GA4GH "
    "standards, DUO terms, consent language, and data sharing obligations - "
    "or you can upload a document for a full compliance review."
)


def run_pipeline(
    researcher_text: str = "",
    follow_up: str = "",
    top_k: int = TOP_K,
    conversation_history: list[dict[str, Any]] | None = None,
) -> PipelineResult:
    result = PipelineResult()
    history = conversation_history or []
    combined_query = f"{researcher_text}\n{follow_up}".strip()

    if not combined_query:
        result.off_topic = True
        result.answer = _OFF_TOPIC_RESPONSE
        result.narrative = _OFF_TOPIC_RESPONSE
        return result

    if _is_off_topic(combined_query):
        result.off_topic = True
        result.answer = _OFF_TOPIC_RESPONSE
        result.narrative = _OFF_TOPIC_RESPONSE
        return result

    try:
        result.domains = classify_domains(combined_query)
        result.retrieved_chunks = retrieve(combined_query, top_k=top_k)

        if not result.retrieved_chunks:
            msg = (
                "No relevant GA4GH policy passages were found in the corpus. "
                "Please index the corpus before running retrieval."
            )
            result.answer = msg
            result.narrative = msg
            return result

        if researcher_text.strip():
            result.chat_mode = "document_review"
            raw_output = detect_gaps(
                researcher_text=researcher_text,
                retrieved_chunks=result.retrieved_chunks,
                follow_up=follow_up,
                conversation_history=history,
            )
            retrieved_article_ids = {chunk.article_id for chunk in result.retrieved_chunks}
            (
                result.verdicts,
                result.flagged_articles,
                result.narrative,
            ) = validate_verdicts(raw_output, retrieved_article_ids)
        else:
            result.chat_mode = "corpus_qa"
            query = follow_up.strip() or combined_query
            result.answer = answer_corpus_question(
                query=query,
                retrieved_chunks=result.retrieved_chunks,
                conversation_history=history,
            )
            retrieved_article_ids = {chunk.article_id for chunk in result.retrieved_chunks}
            valid_cited, flagged = extract_cited_articles(result.answer, retrieved_article_ids)
            result.flagged_articles = flagged
            cited_ids = set(valid_cited)
            result.cited_chunks = [
                chunk for chunk in result.retrieved_chunks if chunk.article_id in cited_ids
            ]
            if not result.cited_chunks:
                result.cited_chunks = result.retrieved_chunks

    except Exception as exc:
        result.error = str(exc)
        msg = (
            f"Analysis encountered an error: {exc}\n\n"
            "Please check that Ollama is running and the corpus has been indexed."
        )
        result.answer = msg
        result.narrative = msg

    return result


def _read_local_document(doc_path: Path) -> str:
    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        pdf = fitz.open(str(doc_path))
        try:
            return "\n\n".join(
                page.get_text("text").strip()
                for page in pdf
                if page.get_text("text").strip()
            )
        finally:
            pdf.close()
    if suffix in {".txt", ".md"}:
        return doc_path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported local document type: {suffix}")


def run_pipeline_from_file(
    doc_path: Path,
    follow_up: str = "",
    top_k: int = TOP_K,
) -> PipelineResult:
    return run_pipeline(_read_local_document(doc_path), follow_up=follow_up, top_k=top_k)

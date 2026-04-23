"""End-to-end pipeline for the Streamlit demo."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz

from config import TOP_K
from generation.gap_detector import answer_corpus_question, detect_gaps
from generation.router import GroundingDecision, RouteDecision, judge_grounding, route_turn
from generation.validator import VerdictItem, extract_cited_articles, validate_verdicts
from retrieval.classifier import classify_domains
from retrieval.retriever import RetrievedChunk, retrieve

_NO_RETRIEVAL_MESSAGES = {
    "corpus_qa": (
        "I couldn't match that clearly to the GA4GH corpus. If you want, ask about a "
        "GA4GH standard, a DUO term, consent language, or upload a document for review."
    ),
    "document_review": (
        "No relevant GA4GH policy passages were found in the corpus. "
        "Please index the corpus before running retrieval."
    ),
}


@dataclass
class PipelineResult:
    """Structured output for one assistant turn."""

    chat_mode: str = "corpus_qa"
    domains: list[str] = field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    verdicts: list[VerdictItem] = field(default_factory=list)
    flagged_articles: list[str] = field(default_factory=list)
    narrative: str = ""
    answer: str = ""
    cited_chunks: list[RetrievedChunk] = field(default_factory=list)
    off_topic: bool = False
    error: str | None = None
    route_intent: str = "corpus_qa"
    route_confidence: str = "low"
    needs_clarification: bool = False
    clarifying_question: str | None = None

    @property
    def is_document_review(self) -> bool:
        return self.chat_mode == "document_review"

    @property
    def has_grounded_sources(self) -> bool:
        return bool(self.cited_chunks)

    @property
    def has_review_findings(self) -> bool:
        return bool(self.verdicts)

    @property
    def can_open_context_rail(self) -> bool:
        return self.has_grounded_sources or self.has_review_findings


def _set_reply(result: PipelineResult, text: str) -> PipelineResult:
    result.answer = text
    result.narrative = text
    return result


def _apply_route_metadata(result: PipelineResult, route: RouteDecision) -> None:
    result.route_intent = route.intent
    result.route_confidence = route.confidence
    result.needs_clarification = route.should_ask_clarifying_question
    result.clarifying_question = route.clarifying_question


def _early_route_result(route: RouteDecision) -> PipelineResult | None:
    result = PipelineResult()
    _apply_route_metadata(result, route)

    if route.intent in {"small_talk", "off_topic_redirect"}:
        result.off_topic = True
        return _set_reply(result, route.reply or "")

    if route.intent == "clarify":
        return _set_reply(result, route.clarifying_question or "")

    return None


def _build_document_review(
    result: PipelineResult,
    researcher_text: str,
    follow_up: str,
    history: list[dict[str, Any]],
) -> PipelineResult:
    raw_output = detect_gaps(
        researcher_text=researcher_text,
        retrieved_chunks=result.retrieved_chunks,
        follow_up=follow_up,
        conversation_history=history,
    )
    retrieved_article_ids = {chunk.article_id for chunk in result.retrieved_chunks}
    result.verdicts, result.flagged_articles, result.narrative = validate_verdicts(
        raw_output,
        retrieved_article_ids,
    )
    return result


def _apply_grounding_result(
    result: PipelineResult,
    grounding: GroundingDecision,
) -> PipelineResult | None:
    result.route_confidence = grounding.confidence
    if grounding.is_answerable:
        return None

    result.retrieved_chunks = []
    if grounding.should_clarify:
        result.route_intent = "clarify"
        result.needs_clarification = True
        result.clarifying_question = grounding.reply
    else:
        result.route_intent = "off_topic_redirect"
        result.off_topic = True
    return _set_reply(result, grounding.reply or "")


def _build_corpus_answer(
    result: PipelineResult,
    query: str,
    history: list[dict[str, Any]],
) -> PipelineResult:
    result.answer = answer_corpus_question(
        query=query,
        retrieved_chunks=result.retrieved_chunks,
        conversation_history=history,
    )
    retrieved_article_ids = {chunk.article_id for chunk in result.retrieved_chunks}
    cited_article_ids, result.flagged_articles = extract_cited_articles(
        result.answer,
        retrieved_article_ids,
    )
    cited_lookup = set(cited_article_ids)
    result.cited_chunks = [
        chunk for chunk in result.retrieved_chunks if chunk.article_id in cited_lookup
    ]
    return result


def run_pipeline(
    researcher_text: str = "",
    follow_up: str = "",
    top_k: int = TOP_K,
    conversation_history: list[dict[str, Any]] | None = None,
) -> PipelineResult:
    history = conversation_history or []
    combined_query = f"{researcher_text}\n{follow_up}".strip()
    route = route_turn(
        user_text=follow_up.strip() or combined_query,
        conversation_history=history,
        has_uploaded_doc=bool(researcher_text.strip()),
    )

    early_result = _early_route_result(route)
    if early_result is not None:
        return early_result

    result = PipelineResult(
        chat_mode="document_review" if route.intent == "document_review" else "corpus_qa"
    )
    _apply_route_metadata(result, route)

    try:
        result.domains = classify_domains(combined_query)
        if route.should_retrieve:
            result.retrieved_chunks = retrieve(combined_query, top_k=top_k)

        if not result.retrieved_chunks:
            return _set_reply(result, _NO_RETRIEVAL_MESSAGES[result.chat_mode])

        if result.is_document_review:
            return _build_document_review(result, researcher_text, follow_up, history)

        query = follow_up.strip() or combined_query
        grounding = judge_grounding(query=query, retrieved_chunks=result.retrieved_chunks)
        blocked_result = _apply_grounding_result(result, grounding)
        if blocked_result is not None:
            return blocked_result

        return _build_corpus_answer(result, query, history)

    except Exception as exc:
        result.error = str(exc)
        return _set_reply(
            result,
            (
                f"Analysis encountered an error: {exc}\n\n"
                "Please check that Ollama is running and the corpus has been indexed."
            ),
        )


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

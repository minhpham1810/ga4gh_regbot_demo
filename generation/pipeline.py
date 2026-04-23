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
from generation.router import judge_grounding, route_turn
from generation.validator import VerdictItem, extract_cited_articles, validate_verdicts
from retrieval.classifier import classify_domains
from retrieval.retriever import RetrievedChunk, retrieve

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
    route_intent: str = "corpus_qa"
    route_confidence: str = "low"
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None

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
    def is_plain_response(self) -> bool:
        return not self.error and not self.is_document_review and not self.has_grounded_sources

    @property
    def can_open_context_rail(self) -> bool:
        return self.has_grounded_sources or self.has_review_findings

    @property
    def is_grounded_answer(self) -> bool:
        return self.route_intent == "corpus_qa" and self.has_grounded_sources


def run_pipeline(
    researcher_text: str = "",
    follow_up: str = "",
    top_k: int = TOP_K,
    conversation_history: list[dict[str, Any]] | None = None,
) -> PipelineResult:
    result = PipelineResult()
    history = conversation_history or []
    combined_query = f"{researcher_text}\n{follow_up}".strip()
    route = route_turn(
        user_text=follow_up.strip() or combined_query,
        conversation_history=history,
        has_uploaded_doc=bool(researcher_text.strip()),
    )
    result.route_intent = route.intent
    result.route_confidence = route.confidence
    result.needs_clarification = route.should_ask_clarifying_question
    result.clarifying_question = route.clarifying_question

    if route.intent in {"small_talk", "off_topic_redirect"}:
        result.off_topic = True
        result.answer = route.reply or ""
        result.narrative = result.answer
        return result

    if route.intent == "clarify":
        result.answer = route.clarifying_question or ""
        result.narrative = result.answer
        return result

    try:
        result.chat_mode = "document_review" if route.intent == "document_review" else "corpus_qa"
        result.domains = classify_domains(combined_query)

        if route.should_retrieve:
            result.retrieved_chunks = retrieve(combined_query, top_k=top_k)

        if not result.retrieved_chunks:
            if route.intent == "document_review":
                msg = (
                    "No relevant GA4GH policy passages were found in the corpus. "
                    "Please index the corpus before running retrieval."
                )
            else:
                msg = (
                    "I couldn't match that clearly to the GA4GH corpus. "
                    "If you want, ask about a GA4GH standard, a DUO term, consent language, "
                    "or upload a document for review."
                )
            result.answer = msg
            result.narrative = msg
            return result

        if route.intent == "document_review":
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
            grounding = judge_grounding(
                query=follow_up.strip() or combined_query,
                retrieved_chunks=result.retrieved_chunks,
            )
            result.route_confidence = grounding.confidence
            if not grounding.is_answerable:
                if grounding.should_clarify:
                    result.route_intent = "clarify"
                    result.needs_clarification = True
                    result.clarifying_question = grounding.reply
                    result.answer = grounding.reply or ""
                    result.narrative = result.answer
                else:
                    result.route_intent = "off_topic_redirect"
                    result.off_topic = True
                    result.answer = grounding.reply or ""
                    result.narrative = result.answer
                result.retrieved_chunks = []
                return result

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

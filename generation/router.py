"""
Intent routing and retrieval-quality gating for chat turns.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import ollama

from config import LLM_MODEL, OLLAMA_BASE_URL
from generation.prompts import load_router_prompt
from retrieval.retriever import RetrievedChunk

_ARTICLE_REF_RE = re.compile(r"\b(?:DUO:\d{7}|article\s+\d+|section\s+\d+(?:\.\d+)*)\b", re.I)

_ROUTER_FALLBACK_REPLY = (
    "I can help with GA4GH standards, DUO terms, consent language, or review an uploaded "
    "document if you want to check it against the corpus."
)
_ROUTER_FALLBACK_CLARIFICATION = (
    "Do you want help with a GA4GH standard, a DUO term, or a document review?"
)


@dataclass
class RouteDecision:
    intent: str
    confidence: str
    reason: str
    should_retrieve: bool
    should_ask_clarifying_question: bool = False
    clarifying_question: str | None = None
    reply: str | None = None


@dataclass
class GroundingDecision:
    is_answerable: bool
    confidence: str
    should_clarify: bool
    should_redirect: bool
    reason: str
    reply: str | None = None


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def _has_article_reference(text: str) -> bool:
    return bool(_ARTICLE_REF_RE.search(text))


def _build_history_block(conversation_history: list[dict[str, Any]]) -> str:
    if not conversation_history:
        return ""
    lines: list[str] = []
    for turn in conversation_history[-6:]:
        role = str(turn.get("role", "user")).capitalize()
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _parse_router_response(raw_text: str) -> dict[str, str]:
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif text.startswith("```"):
        text = text.split("```", 2)[1].strip()
    return json.loads(text)


def _route_with_llm(
    user_text: str,
    conversation_history: list[dict[str, Any]] | None,
    has_uploaded_doc: bool,
) -> RouteDecision:
    client = ollama.Client(host=OLLAMA_BASE_URL)
    user_content = (
        f"## USER TURN\n{user_text.strip()}\n\n"
        f"## HAS_UPLOADED_DOCUMENT\n{str(has_uploaded_doc).lower()}\n\n"
        f"## CONVERSATION HISTORY\n{_build_history_block(conversation_history or [])}\n"
    )
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": load_router_prompt()},
            {"role": "user", "content": user_content},
        ],
    )
    data = _parse_router_response(response["message"]["content"])
    intent = str(data.get("intent", "clarify")).strip() or "clarify"
    confidence = str(data.get("confidence", "low")).strip() or "low"
    reply = str(data.get("reply", "")).strip() or None
    clarifying_question = str(data.get("clarifying_question", "")).strip() or None
    should_retrieve = intent in {"corpus_qa", "document_review"}
    return RouteDecision(
        intent=intent,
        confidence=confidence,
        reason="llm_router",
        should_retrieve=should_retrieve,
        should_ask_clarifying_question=intent == "clarify",
        clarifying_question=clarifying_question,
        reply=reply,
    )


def route_turn(
    user_text: str,
    conversation_history: list[dict[str, Any]] | None = None,
    has_uploaded_doc: bool = False,
) -> RouteDecision:
    normalized = _normalize_text(user_text)
    if not normalized:
        return RouteDecision(
            intent="small_talk",
            confidence="high",
            reason="empty_turn",
            should_retrieve=False,
            reply=_ROUTER_FALLBACK_REPLY,
        )

    if _has_article_reference(normalized):
        return RouteDecision(
            intent="corpus_qa",
            confidence="high",
            reason="explicit_article_reference",
            should_retrieve=True,
        )

    if has_uploaded_doc and ("?" in normalized or len(normalized.split()) >= 6):
        return RouteDecision(
            intent="document_review",
            confidence="high",
            reason="uploaded_document_context",
            should_retrieve=True,
        )

    try:
        decision = _route_with_llm(normalized, conversation_history, has_uploaded_doc)
    except Exception:
        decision = RouteDecision(
            intent="clarify",
            confidence="low",
            reason="router_fallback",
            should_retrieve=False,
            should_ask_clarifying_question=True,
            clarifying_question=_ROUTER_FALLBACK_CLARIFICATION,
        )

    if decision.intent == "small_talk" and not decision.reply:
        decision.reply = _ROUTER_FALLBACK_REPLY
    if decision.intent == "off_topic_redirect" and not decision.reply:
        decision.reply = _ROUTER_FALLBACK_REPLY
    if decision.intent == "clarify" and not decision.clarifying_question:
        decision.clarifying_question = _ROUTER_FALLBACK_CLARIFICATION
    return decision


def judge_grounding(
    query: str,
    retrieved_chunks: list[RetrievedChunk],
) -> GroundingDecision:
    if not retrieved_chunks:
        return GroundingDecision(
            is_answerable=False,
            confidence="low",
            should_clarify=True,
            should_redirect=False,
            reason="no_retrieval_hits",
            reply=_ROUTER_FALLBACK_CLARIFICATION,
        )

    if _has_article_reference(query):
        article_refs = {ref.upper() for ref in _ARTICLE_REF_RE.findall(query)}
        retrieved_ids = {chunk.article_id.upper() for chunk in retrieved_chunks}
        if article_refs & retrieved_ids:
            return GroundingDecision(
                is_answerable=True,
                confidence="high",
                should_clarify=False,
                should_redirect=False,
                reason="matched_article_reference",
            )

    top_score = retrieved_chunks[0].score
    second_score = retrieved_chunks[1].score if len(retrieved_chunks) > 1 else 0.0
    score_gap = top_score - second_score

    if top_score >= 0.72:
        return GroundingDecision(
            is_answerable=True,
            confidence="high",
            should_clarify=False,
            should_redirect=False,
            reason="strong_top_hit",
        )
    if top_score >= 0.58 and score_gap >= 0.08:
        return GroundingDecision(
            is_answerable=True,
            confidence="medium",
            should_clarify=False,
            should_redirect=False,
            reason="good_top_hit_with_gap",
        )

    if top_score >= 0.42:
        return GroundingDecision(
            is_answerable=False,
            confidence="low",
            should_clarify=True,
            should_redirect=False,
            reason="weak_retrieval_clarify",
            reply="I'm not fully confident which GA4GH source you mean. Can you narrow it to a DUO term, a consent topic, or a specific framework question?",
        )

    return GroundingDecision(
        is_answerable=False,
        confidence="low",
        should_clarify=False,
        should_redirect=True,
        reason="retrieval_not_relevant",
        reply="I couldn't match that clearly to the GA4GH corpus. If you want, ask about a GA4GH standard, a DUO term, consent language, or upload a document for review.",
    )

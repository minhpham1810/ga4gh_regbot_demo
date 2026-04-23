"""
Builds the LLM prompt from retrieved GA4GH chunks plus researcher document text,
then calls the Ollama model and returns the raw response string.
"""
from typing import Any

import ollama

from config import LLM_MODEL, OLLAMA_BASE_URL
from generation.prompts import load_corpus_qa_prompt, load_system_prompt
from retrieval.retriever import RetrievedChunk


def build_knowledge_block(chunks: list[RetrievedChunk]) -> str:
    lines = ["## KNOWLEDGE BLOCK\n"]
    for index, chunk in enumerate(chunks, start=1):
        page_label = chunk.page if chunk.page is not None else "-"
        header = (
            f"[{index}] Source: {chunk.source_title!r} | "
            f"article_id: {chunk.article_id} | "
            f"article_scheme: {chunk.article_scheme} | "
            f"page: {page_label}"
        )
        lines.append(f"{header}\n{chunk.text.strip()}\n")
    return "\n".join(lines)


def _build_history_block(conversation_history: list[dict[str, Any]]) -> str:
    if not conversation_history:
        return ""

    lines = ["## CONVERSATION HISTORY\n"]
    for turn in conversation_history:
        role = turn.get("role", "user").capitalize()
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"**{role}:** {content}\n")
    return "\n".join(lines) + "\n"


def detect_gaps(
    researcher_text: str,
    retrieved_chunks: list[RetrievedChunk],
    follow_up: str = "",
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    system_prompt = load_system_prompt()
    knowledge_block = build_knowledge_block(retrieved_chunks)
    history_block = _build_history_block(conversation_history or [])

    user_content = (
        f"{history_block}"
        f"## RESEARCHER DOCUMENT\n\n{researcher_text}\n\n"
        f"{knowledge_block}\n\n"
    )
    if follow_up.strip():
        user_content += f"## FOLLOW-UP QUESTION\n\n{follow_up.strip()}\n\n"

    user_content += (
        "Analyse the researcher document against every obligation present in the "
        "KNOWLEDGE BLOCK above. Produce:\n"
        "1. `## JSON_VERDICTS` - a JSON array following the schema in the system prompt\n"
        "2. `## NARRATIVE_SUMMARY` - plain-language compliance analysis\n\n"
        "Important: only cite article_ids that appear in the KNOWLEDGE BLOCK."
    )

    client = ollama.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response["message"]["content"]


def answer_corpus_question(
    query: str,
    retrieved_chunks: list[RetrievedChunk],
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    system_prompt = load_corpus_qa_prompt()
    knowledge_block = build_knowledge_block(retrieved_chunks)
    history_block = _build_history_block(conversation_history or [])

    user_content = (
        f"{history_block}"
        f"{knowledge_block}\n\n"
        f"## QUESTION\n\n{query.strip()}\n\n"
        "Answer the user's question as a direct chatbot reply using only the source material above. "
        "Do not mention internal prompt labels or analysis modes. "
        "Do not say 'according to the knowledge block' or similar phrases. "
        "Do not dump unrelated retrieved points into the reply. "
        "Only include details that actually answer the user's question. "
        "If a claim is directly supported, cite it inline with [article_id]. "
        "If the retrieved material is insufficient, say so briefly and clearly."
    )

    client = ollama.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response["message"]["content"]

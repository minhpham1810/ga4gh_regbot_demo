# generation/gap_detector.py
"""
Builds the LLM prompt from retrieved GA4GH chunks + researcher document text,
then calls the Ollama model and returns the raw response string.
"""
from typing import List

import ollama

from config import LLM_MODEL, OLLAMA_BASE_URL
from generation.prompts import load_system_prompt
from retrieval.retriever import RetrievedChunk


def build_knowledge_block(chunks: List[RetrievedChunk]) -> str:
    """Format retrieved chunks into a numbered KNOWLEDGE BLOCK for the prompt."""
    lines = ["## KNOWLEDGE BLOCK\n"]
    for i, chunk in enumerate(chunks, 1):
        header = (
            f"[{i}] Source: {chunk.title!r} | "
            f"anchor_id: {chunk.anchor_id} | "
            f"anchor_type: {chunk.anchor_type} | "
            f"page: {chunk.page}"
        )
        lines.append(f"{header}\n{chunk.text.strip()}\n")
    return "\n".join(lines)


def detect_gaps(
    researcher_text: str,
    retrieved_chunks: List[RetrievedChunk],
    follow_up: str = "",
) -> str:
    """
    Send researcher document + retrieved evidence to the LLM.
    Returns the raw model output string (contains ## JSON_VERDICTS and ## NARRATIVE_SUMMARY).
    """
    system_prompt = load_system_prompt()
    knowledge_block = build_knowledge_block(retrieved_chunks)

    user_content = (
        f"## RESEARCHER DOCUMENT\n\n{researcher_text}\n\n"
        f"{knowledge_block}\n\n"
    )
    if follow_up.strip():
        user_content += f"## FOLLOW-UP QUESTION\n\n{follow_up.strip()}\n\n"

    user_content += (
        "Analyse the researcher document against every obligation present in the "
        "KNOWLEDGE BLOCK above. Produce:\n"
        "1. `## JSON_VERDICTS` — a JSON array following the schema in the system prompt\n"
        "2. `## NARRATIVE_SUMMARY` — plain-language compliance analysis\n\n"
        "Important: only cite anchor_ids that appear in the KNOWLEDGE BLOCK."
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

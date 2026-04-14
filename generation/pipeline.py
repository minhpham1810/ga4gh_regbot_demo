# generation/pipeline.py
"""
End-to-end compliance analysis pipeline for a single turn.

Input:  researcher document text (string) + optional follow-up question
Output: PipelineResult with verdicts, narrative, domains, retrieved chunks
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ingestion.loaders import load_document
from retrieval.classifier import classify_domains
from retrieval.retriever import retrieve, RetrievedChunk
from generation.gap_detector import detect_gaps
from generation.validator import validate_verdicts, VerdictItem
from config import TOP_K

# Simple heuristic off-topic guard — checks for clearly non-compliance topics
_OFF_TOPIC_SIGNALS = [
    "weather", "stock price", "stock market", "recipe", "sports",
    "joke", "movie", "translate this", "who is the president",
    "capital of", "how to cook",
]

_COMPLIANCE_SIGNALS = [
    "consent", "data", "compliance", "access", "privacy", "gdpr",
    "research", "ethics", "genomic", "sharing", "duo", "dul",
]


def _is_off_topic(text: str) -> bool:
    lower = text.lower()
    has_off_topic = any(sig in lower for sig in _OFF_TOPIC_SIGNALS)
    has_compliance = any(sig in lower for sig in _COMPLIANCE_SIGNALS)
    return has_off_topic and not has_compliance


@dataclass
class PipelineResult:
    domains: List[str] = field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    verdicts: List[VerdictItem] = field(default_factory=list)
    flagged_anchors: List[str] = field(default_factory=list)
    narrative: str = ""
    off_topic: bool = False
    error: Optional[str] = None


_OFF_TOPIC_RESPONSE = (
    "I'm a GA4GH compliance assistant. Please upload a data use letter, "
    "consent form, or related document to begin a compliance review."
)


def run_pipeline(
    researcher_text: str,
    follow_up: str = "",
    top_k: int = TOP_K,
) -> PipelineResult:
    """
    Run the full compliance analysis pipeline.

    Steps:
      1. Off-topic guard
      2. Domain classification
      3. Semantic retrieval from corpus
      4. LLM gap detection
      5. Citation validation
    """
    result = PipelineResult()

    combined_query = f"{researcher_text}\n{follow_up}".strip()

    if _is_off_topic(combined_query) and not researcher_text.strip():
        result.off_topic = True
        result.narrative = _OFF_TOPIC_RESPONSE
        return result

    if not researcher_text.strip() and not follow_up.strip():
        result.off_topic = True
        result.narrative = _OFF_TOPIC_RESPONSE
        return result

    try:
        result.domains = classify_domains(combined_query)

        result.retrieved_chunks = retrieve(combined_query, top_k=top_k)

        if not result.retrieved_chunks:
            result.narrative = (
                "No relevant GA4GH policy passages were found in the corpus. "
                "Please ingest the corpus first using the sidebar button."
            )
            return result

        raw_output = detect_gaps(
            researcher_text=researcher_text,
            retrieved_chunks=result.retrieved_chunks,
            follow_up=follow_up,
        )

        retrieved_anchor_ids = {c.anchor_id for c in result.retrieved_chunks}
        result.verdicts, result.flagged_anchors, result.narrative = validate_verdicts(
            raw_output, retrieved_anchor_ids
        )

    except Exception as exc:
        result.error = str(exc)
        result.narrative = (
            f"Analysis encountered an error: {exc}\n\n"
            "Please check that Ollama is running and the corpus has been ingested."
        )

    return result


def run_pipeline_from_file(
    doc_path: Path,
    follow_up: str = "",
    top_k: int = TOP_K,
) -> PipelineResult:
    """Convenience wrapper: load a file then run the pipeline."""
    pages = load_document(doc_path)
    full_text = "\n\n".join(text for text, _ in pages)
    return run_pipeline(full_text, follow_up=follow_up, top_k=top_k)

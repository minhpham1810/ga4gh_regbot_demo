# generation/prompts/__init__.py
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_system_prompt() -> str:
    """Load the system prompt from system.md."""
    return (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


def load_corpus_qa_prompt() -> str:
    """Load the corpus QA system prompt from corpus_qa.md."""
    return (_PROMPTS_DIR / "corpus_qa.md").read_text(encoding="utf-8")


def load_router_prompt() -> str:
    """Load the router system prompt from router.md."""
    return (_PROMPTS_DIR / "router.md").read_text(encoding="utf-8")

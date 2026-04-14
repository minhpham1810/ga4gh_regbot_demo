# generation/prompts/__init__.py
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_system_prompt() -> str:
    """Load the system prompt from system.md."""
    return (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")

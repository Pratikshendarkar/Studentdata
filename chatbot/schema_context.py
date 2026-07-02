"""
Loads all semantic layer files and context documents into a single
system prompt string for the Claude API.
Reads: context/schema_prompt.md, context/data_dictionary.md,
       context/sample_questions.md,
       ../rd2_pipeline/rd2_dbt/models/semantic/_sem_models.yml,
       ../rd2_pipeline/rd2_dbt/models/semantic/_metrics.yml
"""

import os
from pathlib import Path
from functools import lru_cache

CHATBOT_DIR  = Path(__file__).parent.parent
CONTEXT_DIR  = CHATBOT_DIR / "context"
PIPELINE_DIR = CHATBOT_DIR.parent / "rd2_pipeline" / "rd2_dbt" / "models" / "semantic"


def _read(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[File not found: {path}]"


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    """
    Assembles the full system prompt from all context files.
    Cached so it's only read from disk once per session.
    """
    sections = [
        ("SCHEMA & BUSINESS CONTEXT", CONTEXT_DIR / "schema_prompt.md"),
        ("COMPLETE DATA DICTIONARY", CONTEXT_DIR / "data_dictionary.md"),
        ("SEMANTIC MODEL DEFINITIONS (dbt)", PIPELINE_DIR / "_sem_models.yml"),
        ("METRICS CATALOG (dbt)", PIPELINE_DIR / "_metrics.yml"),
        ("FEW-SHOT SQL EXAMPLES", CONTEXT_DIR / "sample_questions.md"),
    ]

    parts = []
    for title, path in sections:
        content = _read(path)
        parts.append(f"## {title}\n\n{content}")

    return "\n\n{'='*80}\n\n".join(parts)


def get_system_prompt() -> str:
    return build_system_prompt()


def reload_context():
    """Force reload context from disk (call after updating context files)."""
    build_system_prompt.cache_clear()
    return build_system_prompt()

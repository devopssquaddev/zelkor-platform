import os

import pytest


def llm_model_or_skip() -> str:
    """Return DEFAULT_LLM_MODEL from the environment or skip live LLM tests."""
    model = os.environ.get("DEFAULT_LLM_MODEL") or os.environ.get("LLM_MODEL")
    if not model:
        pytest.skip(
            "DEFAULT_LLM_MODEL not set; install with OPENAI_API_KEY, "
            "OLLAMA_API_KEY, or OLLAMA_LOCAL_HOST"
        )
    return model

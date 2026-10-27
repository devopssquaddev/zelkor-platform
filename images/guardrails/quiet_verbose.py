"""Keep NeMo's verbose mode off unless ZELKOR_LOG_LEVEL=DEBUG.

nemoguardrails 0.24.1 server builds ``LLMRails(config, verbose=True)``. That calls
``set_verbose(True, llm_calls=True)``, which prints events, prompts and completions to the
console and lowers every existing log handler (Zelkor JSON) to WARNING. Prompt bodies must
not reach logs at INFO+ (requirements_platform_logging.md), so we neutralise it here.
"""
from __future__ import annotations

import logging
import os
import sys

_log = logging.getLogger("zelkor-nemo")

_MODULES = ("nemoguardrails.logging.verbose", "nemoguardrails.rails.llm.llmrails")


def _quiet_set_verbose(verbose, *_args, **_kwargs) -> None:
    if verbose:
        _log.debug("NeMo verbose mode suppressed; prompts stay out of logs")


def install() -> bool:
    if os.getenv("ZELKOR_LOG_LEVEL", "INFO").strip().upper() == "DEBUG":
        return False
    for name in _MODULES:
        module = sys.modules.get(name)
        if module is None:
            module = __import__(name, fromlist=["set_verbose"])
        module.set_verbose = _quiet_set_verbose  # llmrails imported the name directly
    return True

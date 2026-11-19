"""Keep NeMo's verbose mode off unless ZELKOR_LOG_LEVEL=DEBUG (and even then keep Zelkor JSON).

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


def _keep_handlers(original):
    """DEBUG: NeMo's verbose console output is wanted, but it must not mute the Zelkor JSON stream
    (set_verbose lowers every existing handler to WARNING, so guardrail_verdict vanished)."""
    def set_verbose(*args, **kwargs):
        levels = [(h, h.level) for h in logging.getLogger().handlers]
        result = original(*args, **kwargs)
        for handler, level in levels:
            handler.setLevel(level)
        return result
    return set_verbose


def install() -> bool:
    if os.getenv("ZELKOR_LOG_LEVEL", "INFO").strip().upper() == "DEBUG":
        for name in _MODULES:
            module = sys.modules.get(name)
            if module is None:
                module = __import__(name, fromlist=["set_verbose"])
            module.set_verbose = _keep_handlers(module.set_verbose)
        return False
    for name in _MODULES:
        module = sys.modules.get(name)
        if module is None:
            module = __import__(name, fromlist=["set_verbose"])
        module.set_verbose = _quiet_set_verbose  # llmrails imported the name directly
    return True


def keep_component_level(name: str = "zelkor-nemo") -> None:
    """Importing nemoguardrails.cli sets the ROOT logger to WARNING. Pin our own logger to
    ZELKOR_LOG_LEVEL so guardrail_verdict (INFO) still reaches stdout, while the root, and
    with it NeMo's INFO logs that carry user text, stays at WARNING."""
    level = logging.getLevelName(os.getenv("ZELKOR_LOG_LEVEL", "INFO").strip().upper())
    logging.getLogger(name).setLevel(level if isinstance(level, int) else logging.INFO)

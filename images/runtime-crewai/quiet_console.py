"""Keep CrewAI's console panels out of stdout below DEBUG.

crewai 1.15's EventListener builds ConsoleFormatter(verbose=True), which prints every tool call's
arguments and output (prompt and tool content) to stdout. Prompt bodies must not reach logs at
INFO+ (requirements_platform_logging.md). The suppression flag is a ContextVar, so ``suppress``
is also called at the start of each turn, inside the task that runs it.
"""
from __future__ import annotations

import os


def enabled() -> bool:
    return os.getenv("ZELKOR_LOG_LEVEL", "INFO").strip().upper() != "DEBUG"


def suppress() -> None:
    if not enabled():
        return
    from crewai_core.printer import set_suppress_console_output

    set_suppress_console_output(True)


def install() -> bool:
    if not enabled():
        return False
    from crewai.events.event_listener import event_listener

    event_listener.formatter.verbose = False
    suppress()
    return True

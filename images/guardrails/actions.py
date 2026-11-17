"""NeMo loads actions.py from the config directory; the logic lives in /app/zelkor_self_check.py."""
from typing import Any, Dict, Optional

from nemoguardrails.actions import action
from nemoguardrails.library.self_check.utils import run_self_check_task

from zelkor_self_check import check


@action(name="zelkor_self_check", is_system_action=True)
async def zelkor_self_check(
    side: str,
    mode: str = "log",
    timeout_ms: int = 5000,
    on_unavailable: str = "allow",
    llms: Optional[Dict[str, Any]] = None,
    llm_task_manager: Any = None,
    context: Optional[dict] = None,
    llm: Any = None,
    config: Any = None,
    **kwargs,
):
    context = context or {}
    task = f"self_check_{side}"
    prompt_context = {"user_input": context.get("user_message"), "bot_response": context.get("bot_message")}

    async def run():
        return await run_self_check_task(
            task=task,
            prompt_context=prompt_context,
            llms=llms or {},
            default_task=task,
            main_llm=llm,
            llm_task_manager=llm_task_manager,
            lowest_temperature=config.lowest_temperature if config is not None else 0.0,
        )

    text = prompt_context["user_input" if side == "input" else "bot_response"]
    return await check(side=side, mode=mode, timeout_ms=int(timeout_ms), text=text, run_task=run,
                       on_unavailable=on_unavailable)

"""AI gateway for ZugaLife standalone.

Minimal gateway that routes all AI calls through Venice.
No budget gates or shield checks — this is a personal standalone app.

When running inside ZugaApp (plugin mode), ZugaApp's gateway is used
instead (it has budget enforcement and shield checks).
"""

import logging

from core.ai.providers import AIResponse, call_venice

logger = logging.getLogger(__name__)


async def ai_call(
    prompt: str,
    task: str = "chat",
    max_tokens: int = 4096,
    messages: list[dict] | None = None,
) -> AIResponse:
    """Single entry point for all AI calls in ZugaLife standalone.

    All tasks route to Venice (privacy-first, zero data retention).
    """
    model = "kimi-k2-5"

    logger.info("AI call: task=%s model=%s", task, model)

    kwargs = {"prompt": prompt, "model": model, "max_tokens": max_tokens}
    if messages is not None:
        kwargs["messages"] = messages

    response = await call_venice(**kwargs)

    logger.info(
        "AI response: model=%s tokens=%d+%d cost=$%.4f",
        response.model,
        response.input_tokens,
        response.output_tokens,
        response.cost,
    )

    return response


class BudgetExhaustedError(Exception):
    """Raised when the daily budget limit has been reached."""
    pass


class PromptBlockedError(Exception):
    """Raised when a prompt is blocked."""
    pass

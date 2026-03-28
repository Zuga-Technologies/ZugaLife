"""AI gateway for ZugaLife standalone.

Routes all AI calls through Venice with optional credit tracking.
When running inside ZugaApp (plugin mode), ZugaApp's gateway is used
instead (it has full budget enforcement, shield checks, and credit tracking).

Credit tracking in standalone mode:
- If ZUGAAPP_CREDITS_URL is set → reports spend via HTTP to ZugaApp
- If shared DB available → writes directly to credit ledger
- Otherwise → logs spend only (NullCreditClient)
"""

import logging

from core.ai.providers import AIResponse, call_venice

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when the daily budget limit has been reached."""
    pass


class CreditBlockedError(Exception):
    """Raised when a user has no credits."""
    pass


class PromptBlockedError(Exception):
    """Raised when a prompt is blocked."""
    pass


async def ai_call(
    prompt: str,
    task: str = "chat",
    max_tokens: int = 4096,
    messages: list[dict] | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
) -> AIResponse:
    """Single entry point for all AI calls in ZugaLife standalone.

    All tasks route to Venice (privacy-first, zero data retention).
    If user_id/user_email are provided, credit checks and tracking are applied.
    """
    from core.credits.client import get_credit_client, dollars_to_tokens

    credit_client = get_credit_client()

    model = "kimi-k2-5"

    # Pre-flight token check with estimated cost (only if user context available)
    if user_id and user_email:
        estimated_cost = _estimate_call_cost(max_tokens)
        estimated_tokens = dollars_to_tokens(estimated_cost)
        if not await credit_client.can_spend(user_id, user_email, estimated_tokens):
            raise CreditBlockedError("Insufficient ZugaTokens")

    logger.info("AI call: task=%s model=%s user=%s", task, model, user_id or "anonymous")

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

    # Record token spend
    if user_id:
        await credit_client.record_spend(
            user_id=user_id,
            tokens=dollars_to_tokens(response.cost),
            cost_usd=response.cost,
            service="venice",
            reason=task,
            model=response.model,
        )

    return response


def _estimate_call_cost(max_tokens: int) -> float:
    """Rough cost estimate for Venice calls before making them."""
    # Venice pricing: ~$0.50/M input, ~$2.50/M output (kimi-k2-5)
    input_rate, output_rate = 0.5, 2.5
    return (500 * input_rate + max_tokens * output_rate) / 1_000_000

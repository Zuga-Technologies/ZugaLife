"""AI providers for ZugaLife standalone.

SECURITY: Only Venice is available. Therapist data must NEVER
be sent to providers that retain user data (OpenAI, Anthropic, etc.).
Venice has zero data retention by design.
"""

from dataclasses import dataclass

import httpx

from config import settings


@dataclass
class AIResponse:
    """Standardized response from an AI provider."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


# Cost per 1M tokens (input, output)
_PRICING: dict[str, tuple[float, float]] = {
    "venice/kimi-k2-5": (0.75, 3.75),
}


async def call_venice(
    prompt: str,
    model: str = "kimi-k2-5",
    max_tokens: int = 4096,
    messages: list[dict] | None = None,
) -> AIResponse:
    """Venice AI — privacy-first inference. Zero data retention.

    SECURITY: This is the ONLY provider authorized for therapist data.
    Uses OpenAI-compatible /chat/completions endpoint.
    """
    if not settings.venice_api_key:
        raise RuntimeError("VENICE_API_KEY not configured")

    if messages is None:
        messages = [{"role": "user", "content": prompt}]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.venice.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.venice_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()

    usage = data["usage"]
    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()

    # Kimi K2.5 sometimes puts entire response in reasoning_content
    # with nothing in content. Use reasoning as fallback.
    if not content and msg.get("reasoning_content"):
        content = msg["reasoning_content"].strip()

    input_rate, output_rate = _PRICING.get(f"venice/{model}", (0.75, 3.75))
    cost = (usage["prompt_tokens"] * input_rate + usage["completion_tokens"] * output_rate) / 1_000_000

    return AIResponse(
        content=content,
        model=model,
        input_tokens=usage["prompt_tokens"],
        output_tokens=usage["completion_tokens"],
        cost=cost,
    )

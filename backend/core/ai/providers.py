"""AI providers for ZugaLife standalone.

SECURITY: Only Venice is available. Therapist data must NEVER
be sent to providers that retain user data (OpenAI, Anthropic, etc.).
Venice has zero data retention by design.
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Cap retry waits so a misbehaving Retry-After can't stall a request indefinitely.
_VENICE_429_RETRY_CAP_SECONDS = 5.0
_VENICE_429_DEFAULT_BACKOFF_SECONDS = 1.5

# Long-lived HTTP client reused across calls (mirrors ZugaApp providers).
# Keep-alive eliminates TLS+TCP handshake on each Venice call.
_VENICE_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)
_venice_client: httpx.AsyncClient | None = None


def _get_venice_client() -> httpx.AsyncClient:
    global _venice_client
    if _venice_client is None:
        _venice_client = httpx.AsyncClient(
            base_url="https://api.venice.ai",
            timeout=120.0,
            limits=_VENICE_HTTP_LIMITS,
        )
    return _venice_client


class RateLimitError(Exception):
    """Upstream AI provider returned 429 (rate limited). Retry after a short delay."""

    def __init__(self, provider: str, retry_after: float | None = None):
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"{provider} rate-limited (retry_after={retry_after})")


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

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }

    client = _get_venice_client()
    # Single retry on 429 with bounded backoff (mirrors ZugaApp/backend/core/ai/providers.py).
    for attempt in range(2):
        response = await client.post(
            "/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.venice_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code != 429:
            break

        retry_after_hdr = response.headers.get("retry-after")
        try:
            retry_after = float(retry_after_hdr) if retry_after_hdr else None
        except ValueError:
            retry_after = None

        if attempt == 0:
            wait = min(retry_after or _VENICE_429_DEFAULT_BACKOFF_SECONDS, _VENICE_429_RETRY_CAP_SECONDS)
            logger.warning("venice 429 — retrying in %.2fs (retry_after=%s)", wait, retry_after_hdr)
            await asyncio.sleep(wait)
            continue

        raise RateLimitError("venice", retry_after=retry_after)

    response.raise_for_status()
    data = response.json()

    usage = data["usage"]
    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()

    input_rate, output_rate = _PRICING.get(f"venice/{model}", (0.75, 3.75))
    cost = (usage["prompt_tokens"] * input_rate + usage["completion_tokens"] * output_rate) / 1_000_000

    return AIResponse(
        content=content,
        model=model,
        input_tokens=usage["prompt_tokens"],
        output_tokens=usage["completion_tokens"],
        cost=cost,
    )

import base64
import time
from typing import Any

from ..config import LLMConfig
from .base import LLMClient, LLMResult

# Models that accept server-side refusal fallbacks. A refused line just means
# silence here, but the fallback keeps an over-cautious classifier from muting the booth.
FALLBACK_MODELS = ("claude-sonnet-5-5", "claude-opus-5", "claude-fable-5-1")


class AnthropicClient(LLMClient):
    def __init__(self, cfg: LLMConfig) -> None:
        super().__init__(cfg)
        from anthropic import AsyncAnthropic

        # Reads ANTHROPIC_API_KEY (or an `ant auth login` profile).
        self._client = AsyncAnthropic(timeout=cfg.timeout_seconds, max_retries=1)

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], images: list[bytes] | None = None
    ) -> LLMResult:
        content: list[dict[str, Any]] = []
        if images and self.cfg.vision:
            for img in images:
                content.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(img).decode()},
                    }
                )
        content.append({"type": "text", "text": user})

        params: dict[str, Any] = {
            "model": self.cfg.model,
            "max_tokens": self.cfg.max_tokens,
            # Personas + league context are identical every shot, so cache them.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if self.cfg.effort and self.cfg.effort != "none":   # "none" is OpenAI's; Claude just omits it
            params["output_config"]["effort"] = self.cfg.effort

        started = time.perf_counter()
        if self.cfg.model.startswith(FALLBACK_MODELS):
            resp = await self._client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            )
        else:
            resp = await self._client.messages.create(**params)
        latency = time.perf_counter() - started

        text = ""
        if resp.stop_reason != "refusal":
            text = next((b.text for b in resp.content if b.type == "text"), "")
        usage = resp.usage
        return LLMResult(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None),
            latency_seconds=latency,
        )

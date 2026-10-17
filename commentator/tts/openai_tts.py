import os

import httpx
import numpy as np

from ..config import TTSConfig
from .base import TTS, Audio

PCM_SAMPLE_RATE = 24_000  # OpenAI's "pcm" format: 24 kHz, 16-bit signed LE, mono


class OpenAITTS(TTS):
    concurrent = True  # network calls: voice all flight outcomes at once, not one after another
    remote = True  # requests can stall; the speech queue enforces the real per-request deadline

    def __init__(self, cfg: TTSConfig) -> None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.cfg = cfg
        self._http = httpx.AsyncClient(
            base_url="https://api.openai.com/v1", headers={"Authorization": f"Bearer {key}"}, timeout=30
        )

    async def synthesize(self, text: str, voice: str, instructions: str | None = None) -> Audio:
        body = {
            "model": self.cfg.openai_model,
            "voice": voice,
            "input": text,
            "response_format": "pcm",
        }
        # Only the tts-1 family takes `speed`; gpt-4o-mini-tts rejects it. Send it only for a model
        # that supports it and only when it's actually changed, so the default path can't 400.
        if self.cfg.speed != 1.0 and self.cfg.openai_model.startswith("tts-1"):
            body["speed"] = self.cfg.speed
        # `instructions` (delivery steering) is a gpt-4o-tts feature; tts-1 ignores/rejects it.
        if instructions and not self.cfg.openai_model.startswith("tts-1"):
            body["instructions"] = instructions
        resp = await self._http.post("/audio/speech", json=body)
        resp.raise_for_status()
        pcm = np.frombuffer(resp.content, dtype="<i2").astype("float32") / 32768.0
        return Audio(samples=pcm, sample_rate=PCM_SAMPLE_RATE)

import asyncio
from pathlib import Path

from ..config import TTSConfig
from .base import TTS, Audio


class KokoroTTS(TTS):
    """Local Kokoro via ONNX Runtime. Runs on CPU so the GPU stays with GSPro."""

    def __init__(self, cfg: TTSConfig) -> None:
        from kokoro_onnx import Kokoro

        for p in (cfg.kokoro_model, cfg.kokoro_voices):
            if not Path(p).exists():
                raise FileNotFoundError(f"Kokoro file not found: {p}. See docs/setup.md, Setup.")
        self.cfg = cfg
        self._kokoro = Kokoro(cfg.kokoro_model, cfg.kokoro_voices)

    async def synthesize(self, text: str, voice: str, instructions: str | None = None) -> Audio:
        samples, sr = await asyncio.to_thread(
            self._kokoro.create, text, voice=voice, speed=self.cfg.speed, lang="en-us"
        )
        return Audio(samples=samples.astype("float32"), sample_rate=sr)

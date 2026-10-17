from .base import TTS, Audio


class ConsoleTTS(TTS):
    """No audio. Lines are printed by the speech queue; useful for testing anywhere."""

    async def synthesize(self, text: str, voice: str, instructions: str | None = None) -> Audio | None:
        return None

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class Audio:
    samples: np.ndarray  # float32 mono, -1..1
    sample_rate: int


class TTS(ABC):
    # True when synthesising several lines at once is a win (a network provider): the pre-shot
    # voicing of all flight outcomes can then fire in parallel. False for a local-CPU model
    # (Kokoro), where concurrent synths just fight for the same cores and starve OCR.
    concurrent: bool = False
    # True for a network provider whose requests can stall; the speech queue then caps each request
    # with a timeout and retries when there's time. A local model gets no timeout (it doesn't stall,
    # and cancelling its await wouldn't stop the CPU work anyway).
    remote: bool = False

    @abstractmethod
    async def synthesize(self, text: str, voice: str, instructions: str | None = None) -> Audio | None:
        """Return audio, or None for providers that don't produce sound (console). `instructions`
        steers delivery (tone/pacing) on providers that support it; others ignore it."""

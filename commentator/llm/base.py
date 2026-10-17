from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..config import LLMConfig


@dataclass
class LLMResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    latency_seconds: float = 0.0


class LLMClient(ABC):
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg

    @property
    def provider(self) -> str:
        return self.cfg.provider

    @property
    def model(self) -> str:
        return self.cfg.model

    @abstractmethod
    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], images: list[bytes] | None = None
    ) -> LLMResult:
        """Return model output constrained to `schema`. `images` are JPEG bytes."""

from ..config import LLMConfig
from .base import LLMClient, LLMResult


def build_llm(cfg: LLMConfig) -> LLMClient:
    if cfg.provider == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(cfg)
    if cfg.provider == "openai":
        from .openai_client import OpenAIClient

        return OpenAIClient(cfg)
    from .ollama_client import OllamaClient

    return OllamaClient(cfg)


__all__ = ["LLMClient", "LLMResult", "build_llm"]

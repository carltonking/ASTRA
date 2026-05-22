"""LLM provider factory — creates the appropriate provider from config."""

import os

from astra.llm.provider import LLMProvider
from astra.llm.anthropic_provider import AnthropicProvider
from astra.llm.openai_provider import OpenAIProvider
from astra.llm.retry import RetryingProvider
from astra.llm.errors import LLMConfigurationError

_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def register_provider(name: str, provider_cls: type[LLMProvider]) -> None:
    """Register a custom LLM provider implementation."""
    _PROVIDER_REGISTRY[name] = provider_cls


def create_llm_provider(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    max_retries: int = 3,
) -> LLMProvider:
    """Create and return a configured LLM provider.

    Args:
        provider: Provider name ('anthropic', 'openai', etc.).
                  Defaults to ASTRA_LLM_PROVIDER env or 'anthropic'.
        api_key: API key. Defaults to ANTHROPIC_API_KEY or OPENAI_API_KEY env.
        model: Model name. Defaults to provider-specific default.
        max_retries: Number of retries for transient failures.

    Returns:
        A configured LLMProvider instance (wrapped in RetryingProvider).

    Raises:
        LLMConfigurationError: If no valid provider can be created.
    """
    provider_name = provider or os.environ.get("ASTRA_LLM_PROVIDER", "anthropic")

    provider_cls = _PROVIDER_REGISTRY.get(provider_name)
    if provider_cls is None:
        raise LLMConfigurationError(
            f"Unsupported LLM provider: {provider_name}. "
            f"Available: {', '.join(sorted(_PROVIDER_REGISTRY))}"
        )

    if provider_name == "anthropic":
        resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        resolved_model = model or "claude-sonnet-4-20250514"
    elif provider_name == "openai":
        resolved_api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        resolved_model = model or "gpt-4o"
    else:
        resolved_api_key = api_key or ""
        resolved_model = model or ""

    inner: LLMProvider = provider_cls(
        api_key=resolved_api_key,
        model=resolved_model,
    )

    if max_retries > 0:
        return RetryingProvider(inner, max_retries=max_retries)

    return inner

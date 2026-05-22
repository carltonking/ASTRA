"""LLM provider exceptions."""


class LLMProviderError(Exception):
    """Base exception for all LLM provider errors."""


class LLMConfigurationError(LLMProviderError):
    """Raised when the LLM provider is misconfigured."""

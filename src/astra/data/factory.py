"""Data provider registry and factory — mirrors llm/factory.py pattern."""

from typing import Any

from astra.data.provider import DataProvider

_PROVIDER_REGISTRY: dict[str, type[DataProvider]] = {}


def register_provider(name: str, provider_cls: type[DataProvider]) -> None:
    _PROVIDER_REGISTRY[name.lower()] = provider_cls


def create_data_provider(
    source: str = "yfinance",
    **kwargs: Any,
) -> DataProvider:
    source = source.lower()
    if source not in _PROVIDER_REGISTRY:
        msg = f"Unknown data provider: {source}. Available: {list(_PROVIDER_REGISTRY)}"
        raise ValueError(msg)
    return _PROVIDER_REGISTRY[source](**kwargs)


def list_providers() -> list[str]:
    return list(_PROVIDER_REGISTRY)

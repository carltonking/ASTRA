"""Broker registry and factory — mirrors llm/factory.py pattern."""

import os
from typing import Any

from astra.broker.base import Broker

_BROKER_REGISTRY: dict[str, type[Broker]] = {}


def register_broker(name: str, broker_cls: type[Broker]) -> None:
    _BROKER_REGISTRY[name.lower()] = broker_cls


def create_broker(broker: str | None = None, **kwargs: Any) -> Broker:
    broker_name = (broker or os.getenv("ASTRA_BROKER", "alpaca")).lower()
    if broker_name not in _BROKER_REGISTRY:
        msg = f"Unknown broker: {broker_name}. Available: {list(_BROKER_REGISTRY)}"
        raise ValueError(msg)
    return _BROKER_REGISTRY[broker_name](**kwargs)


def list_brokers() -> list[str]:
    return list(_BROKER_REGISTRY)

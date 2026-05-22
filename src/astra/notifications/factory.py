"""Notifier registry and factory — mirrors llm/factory.py pattern."""

from typing import Any

from astra.notifications.base import Notifier

_NOTIFIER_REGISTRY: dict[str, type[Notifier]] = {}


def register_notifier(name: str, notifier_cls: type[Notifier]) -> None:
    _NOTIFIER_REGISTRY[name.lower()] = notifier_cls


def create_notifiers(**kwargs: Any) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for name, cls in _NOTIFIER_REGISTRY.items():
        try:
            notifiers.append(cls(**kwargs))
        except Exception as e:
            print(f"Notifications: failed to initialize {name}: {e}")
    return notifiers

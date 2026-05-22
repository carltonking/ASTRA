"""Notifications — alerts for monitoring, graduation, and pipeline events."""

from astra.notifications.base import Notifier, NotificationLevel
from astra.notifications.factory import create_notifiers, register_notifier

# Ensure built-in notifiers are registered
import astra.notifications.slack  # noqa: F401
import astra.notifications.email  # noqa: F401

__all__ = [
    "Notifier",
    "NotificationLevel",
    "create_notifiers",
    "register_notifier",
]

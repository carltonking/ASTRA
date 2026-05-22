"""Notifier ABC — abstract interface for notification channels."""

from abc import ABC, abstractmethod
from enum import Enum


class NotificationLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class Notifier(ABC):
    @abstractmethod
    def send(
        self,
        subject: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
    ) -> bool:
        ...

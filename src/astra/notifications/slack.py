"""Slack notifier — sends messages via incoming webhook."""

import os

import requests

from astra.notifications.base import Notifier, NotificationLevel
from astra.notifications.factory import register_notifier


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str | None = None):
        self._webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")
        self._session = requests.Session()

    def send(
        self,
        subject: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
    ) -> bool:
        if not self._webhook_url:
            return False
        emoji = {
            NotificationLevel.INFO: ":information_source:",
            NotificationLevel.WARNING: ":warning:",
            NotificationLevel.ERROR: ":x:",
            NotificationLevel.SUCCESS: ":white_check_mark:",
        }.get(level, ":information_source:")
        payload = {
            "text": f"{emoji} *{subject}*\n{message}",
            "mrkdwn": True,
        }
        try:
            resp = self._session.post(
                self._webhook_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Slack notifier failed: {e}")
            return False


register_notifier("slack", SlackNotifier)

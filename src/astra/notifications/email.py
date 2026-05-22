"""Email notifier — sends via SMTP."""

import os
import smtplib
from email.mime.text import MIMEText
from typing import Any

from astra.notifications.base import Notifier, NotificationLevel
from astra.notifications.factory import register_notifier


class EmailNotifier(Notifier):
    def __init__(self, **kwargs: Any):
        self._host = kwargs.get("host") or os.getenv("SMTP_HOST", "")
        self._port = int(kwargs.get("port") or os.getenv("SMTP_PORT", "587"))
        self._user = kwargs.get("user") or os.getenv("SMTP_USER", "")
        self._password = kwargs.get("password") or os.getenv("SMTP_PASS", "")
        self._from_addr = kwargs.get("from_addr") or os.getenv("NOTIFY_FROM", self._user)
        self._to_addr = kwargs.get("to_addr") or os.getenv("NOTIFY_TO", "")

    def send(
        self,
        subject: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
    ) -> bool:
        if not self._host or not self._to_addr:
            return False
        prefix = f"[{level.value}] "
        full_subject = f"{prefix}{subject}"
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = full_subject
        msg["From"] = self._from_addr
        msg["To"] = self._to_addr
        try:
            with smtplib.SMTP(self._host, self._port) as server:
                server.starttls()
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"Email notifier failed: {e}")
            return False


register_notifier("email", EmailNotifier)

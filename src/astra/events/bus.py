"""Async event bus with optional Redis publication."""

import asyncio
import json
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from astra.db.models import EventRecord
from astra.db.session import Database


@dataclass(frozen=True)
class AstraEvent:
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


EventHandler = Callable[[AstraEvent], Awaitable[None] | None]


class EventBus(Protocol):
    async def publish(self, event: AstraEvent) -> None:
        ...

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        ...


class InMemoryEventBus:
    def __init__(self, db: Database | None = None):
        self._db = db
        self._handlers: dict[str, list[EventHandler]] = {}
        self._history: list[AstraEvent] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: AstraEvent) -> None:
        self._history.append(event)
        if self._db is not None:
            await self._persist(event)
        handlers = self._handlers.get(event.event_type, []) + self._handlers.get("*", [])
        for handler in handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

    def history(self) -> list[AstraEvent]:
        return list(self._history)

    async def _persist(self, event: AstraEvent) -> None:
        if self._db is None:
            return
        async with self._db.session() as session:
            session.add(
                EventRecord(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.payload,
                    metadata_=event.metadata,
                    created_at=event.created_at,
                )
            )


class RedisEventBus(InMemoryEventBus):
    def __init__(
        self,
        db: Database | None = None,
        redis_url: str | None = None,
        channel: str = "astra.events",
    ):
        super().__init__(db=db)
        self._redis_url = redis_url or os.environ.get("ASTRA_REDIS_URL", "redis://localhost:6379/0")
        self._channel = channel
        self._client: Any | None = None

    async def publish(self, event: AstraEvent) -> None:
        await super().publish(event)
        client = await self._get_client()
        await client.publish(self._channel, json.dumps(event.to_dict(), default=str))

    async def _get_client(self) -> Any:
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

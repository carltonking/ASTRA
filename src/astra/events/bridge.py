"""Bridge legacy synchronous pipeline events into durable async events."""

import asyncio
import threading
from typing import Any

from astra.events.bus import AstraEvent, EventBus
from astra.pipeline.events import PipelineEventBus


class DurablePipelineEventBridge:
    """Subscribe to `PipelineEventBus` and publish `AstraEvent` records."""

    def __init__(
        self,
        pipeline_bus: PipelineEventBus,
        durable_bus: EventBus,
        aggregate_type: str = "pipeline",
        aggregate_id: str = "global",
    ):
        self._durable_bus = durable_bus
        self._aggregate_type = aggregate_type
        self._aggregate_id = aggregate_id
        pipeline_bus.subscribe(self.forward)

    def forward(self, event: str, data: dict[str, Any]) -> None:
        aggregate_id = str(
            data.get("pipeline_id")
            or data.get("deployment_id")
            or data.get("session_id")
            or self._aggregate_id
        )
        durable_event = AstraEvent(
            event_type=event,
            aggregate_type=self._aggregate_type,
            aggregate_id=aggregate_id,
            payload=data,
        )
        self._publish_threadsafe(durable_event)

    def _publish_threadsafe(self, event: AstraEvent) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._durable_bus.publish(event))
        except RuntimeError:
            threading.Thread(
                target=lambda: asyncio.run(self._durable_bus.publish(event)),
                daemon=True,
            ).start()

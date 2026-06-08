"""Turn Pipeline delivery adapters for non-user surfaces."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.channels import ChannelMessage
from app.providers.base import StreamEvent


@dataclass
class SystemDeliveryAdapter:
    """Collect turn events without writing to a user-channel transport."""

    surface: str = "system"
    events: list[StreamEvent] = field(default_factory=list)

    @property
    def final_text(self) -> str:
        """Return concatenated assistant delta text from collected events."""
        return "".join(
            event.get("content", "") for event in self.events if event.get("type") == "delta"
        ).strip()

    async def deliver(
        self,
        stream: AsyncIterator[StreamEvent],
        _message: ChannelMessage,
    ) -> AsyncIterator[bytes]:
        """Drain the stream and keep events for the caller to inspect."""
        async for event in stream:
            self.events.append(event)
        if False:
            yield b""

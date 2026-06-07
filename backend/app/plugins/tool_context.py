"""Runtime context passed into trusted Python plugin tool factories."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.send_message import SendFn


@dataclass(frozen=True)
class ToolContext:
    """Per-turn binding for trusted Python plugin tool factories."""

    workspace_id: uuid.UUID
    workspace_root: Path
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    model_id: str | None = None
    surface: str | None = None
    send_fn: SendFn | None = None

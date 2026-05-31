"""Per-tool Telegram trace state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ToolLineState:
    """State for one Telegram tool trace line."""

    call_id: str
    display: str
    compact: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    result_line: str | None = None
    progress_line: str | None = None

    @property
    def rendered_line(self) -> str:
        """Current display line: terminal result, progress, or in-flight label."""
        return self.result_line or self.progress_line or self.display

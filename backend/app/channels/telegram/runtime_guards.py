"""Runtime guards for Telegram process ownership.

Polling is a singleton per bot token: Telegram rejects concurrent
``getUpdates`` consumers, and repeated restarts can also flood
``setMyCommands``. These helpers keep those operational concerns out of
the message handler code.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import tempfile
import time
from pathlib import Path

COMMAND_REFRESH_COOLDOWN_SECONDS = 3600.0


def _token_key(token: str) -> str:
    """Return a filesystem-safe, non-secret key for a bot token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _state_path(kind: str, token: str) -> Path:
    """Return the cross-restart Telegram guard path for ``kind``."""
    return Path(tempfile.gettempdir()) / f"pawrrtal-telegram-{kind}-{_token_key(token)}"


class TelegramPollingLock:
    """Advisory lock proving this process owns Telegram polling."""

    def __init__(self, *, token: str) -> None:
        self._path = _state_path("polling.lock", token)
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        """Path to the lock file, for diagnostics."""
        return self._path

    def acquire(self) -> bool:
        """Try to claim polling ownership without blocking."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii"))
        self._fd = fd
        return True

    def release(self) -> None:
        """Release polling ownership if this process holds it."""
        if self._fd is None:
            return
        with contextlib.suppress(OSError):
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(self._fd)
        self._fd = None


def should_refresh_commands(*, token: str, now: float | None = None) -> bool:
    """Return whether command registration is outside the cooldown window."""
    current_time = time.time() if now is None else now
    path = _state_path("commands.next", token)
    try:
        next_allowed = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return True
    return current_time >= next_allowed


def defer_command_refresh(
    *,
    token: str,
    seconds: float = COMMAND_REFRESH_COOLDOWN_SECONDS,
    now: float | None = None,
) -> None:
    """Persist the next time command registration may run."""
    current_time = time.time() if now is None else now
    path = _state_path("commands.next", token)
    path.write_text(str(current_time + max(seconds, 0.0)), encoding="utf-8")

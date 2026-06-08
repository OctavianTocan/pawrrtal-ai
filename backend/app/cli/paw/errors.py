"""Exit codes and PawError hierarchy.

Exit codes (documented in --help footer):
    0  success
    1  local error (parse, fs, config)
    2  missing argument / typer usage error
    3  auth error
    4  backend unreachable
    5  provider/API error (HTTP 4xx/5xx other than 401)
    6  verification failed
    7  tracked dev backend PID is dead (paw dev status; distinct from 4)
"""

from __future__ import annotations

import typer

EXIT_DEV_DEAD = 7


class PawError(typer.Exit):
    """Base class with a hint and an explicit exit code."""

    def __init__(self, message: str, *, exit_code: int, hint: str | None = None) -> None:
        self.message = message
        self.hint = hint
        super().__init__(code=exit_code)


class LocalError(PawError):
    """Generic local-side failure: bad args, missing file, config drift (exit 1)."""

    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=1, hint=hint)


class AuthError(PawError):
    """Authentication missing or rejected by the backend (exit 3)."""

    def __init__(
        self,
        msg: str = "Not authenticated.",
        hint: str | None = "Run `paw login`.",
    ) -> None:
        super().__init__(msg, exit_code=3, hint=hint)


class BackendUnreachableError(PawError):
    """Network-level failure reaching the backend (exit 4).

    Distinct from ``EXIT_DEV_DEAD`` (exit 7), which signals that ``paw dev``
    has a tracked PID in state but the process itself is gone.
    """

    def __init__(
        self,
        msg: str,
        hint: str | None = "Is `just dev` running?",
    ) -> None:
        super().__init__(msg, exit_code=4, hint=hint)


class ApiError(PawError):
    """Backend returned an HTTP error other than 401 auth (exit 5)."""

    def __init__(
        self,
        msg: str,
        hint: str | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(msg, exit_code=5, hint=hint)
        self.status_code = status_code


class VerificationFailedError(PawError):
    """A ``paw verify`` scenario completed but its assertions failed (exit 6)."""

    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=6, hint=hint)

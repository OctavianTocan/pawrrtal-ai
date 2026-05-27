"""Exit codes and PawError hierarchy.

Exit codes (documented in --help footer):
    0  success
    1  local error (parse, fs, config)
    2  missing argument / typer usage error
    3  auth error
    4  backend unreachable
    5  provider/API error (HTTP 4xx/5xx other than 401)
    6  verification failed
"""

from __future__ import annotations

import typer


class PawError(typer.Exit):
    """Base class with a hint and an explicit exit code."""

    def __init__(self, message: str, *, exit_code: int, hint: str | None = None) -> None:
        self.message = message
        self.hint = hint
        super().__init__(code=exit_code)


class LocalError(PawError):
    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=1, hint=hint)


class AuthError(PawError):
    def __init__(
        self,
        msg: str = "Not authenticated.",
        hint: str | None = "Run `paw login`.",
    ) -> None:
        super().__init__(msg, exit_code=3, hint=hint)


class BackendUnreachable(PawError):
    def __init__(
        self,
        msg: str,
        hint: str | None = "Is `just dev` running?",
    ) -> None:
        super().__init__(msg, exit_code=4, hint=hint)


class ApiError(PawError):
    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=5, hint=hint)


class VerificationFailed(PawError):
    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=6, hint=hint)

"""paw — Pawrrtal Agent CLI."""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str) -> object:
    """Load the Typer app lazily so submodule imports stay lightweight."""
    if name == "app":
        from .main import app  # noqa: PLC0415

        return app
    raise AttributeError(name)

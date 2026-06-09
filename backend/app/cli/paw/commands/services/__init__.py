"""Public surface for ``paw services``."""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str) -> object:
    """Load the Typer app lazily so services can run standalone."""
    if name == "app":
        from app.cli.paw.commands.services.cli import app  # noqa: PLC0415

        return app
    raise AttributeError(name)

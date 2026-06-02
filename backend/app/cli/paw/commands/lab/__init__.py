"""Experimental ``paw lab`` command group."""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name: str) -> object:
    """Load the Typer app lazily so flow helpers do not import bench providers."""
    if name == "app":
        from .cli import app  # noqa: PLC0415

        return app
    raise AttributeError(name)

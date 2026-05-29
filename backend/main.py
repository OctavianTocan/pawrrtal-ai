"""FastAPI application entry point."""

from __future__ import annotations

from app.infrastructure.app_factory import create_app, with_cors

app = with_cors(create_app())  # type: ignore[assignment]

__all__ = ["app", "create_app", "with_cors"]

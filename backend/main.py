"""FastAPI application entry point."""

from __future__ import annotations

from typing import Any

from app.infrastructure.app_factory import create_app, with_cors

app: Any = with_cors(create_app())

__all__ = ["app", "create_app", "with_cors"]

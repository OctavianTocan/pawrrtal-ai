"""CORS wrapper for the whole ASGI app."""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.infrastructure.config import settings


def with_cors(asgi_app: ASGIApp) -> ASGIApp:
    """Wrap the whole ASGI app so unhandled errors still include CORS headers."""
    return CORSMiddleware(
        asgi_app,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

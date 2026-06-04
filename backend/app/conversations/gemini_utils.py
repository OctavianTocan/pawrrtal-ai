"""Lightweight Gemini helpers for one-off, non-streaming calls."""

from __future__ import annotations

from functools import cache

from google import genai
from google.genai import types

from app.infrastructure.config import settings
from app.providers.catalog import MODEL_CATALOG
from app.providers.model_id import Host


@cache
def _get_client() -> genai.Client:
    """Return a shared Gemini client, creating it on first call."""
    return genai.Client(api_key=settings.google_api_key)


def _first_gemini_slug() -> str:
    """Return the bare slug of the first Gemini (``google_ai`` host) catalog entry.

    These calls go through the Gemini SDK, so the fallback model must be a
    Gemini model — the first *catalog* entry overall can belong to another
    host (e.g. Anthropic), and handing its slug to the Gemini SDK would
    fail. Catalog-driven so it tracks the catalog without a hardcoded slug.
    """
    for entry in MODEL_CATALOG:
        if entry.host is Host.google_ai:
            return entry.model
    raise RuntimeError("no google_ai model in the catalog for Gemini title generation")


async def generate_text_once(prompt: str, model_id: str | None = None) -> str:
    """Send a single prompt to Gemini and return the text response.

    Used for short utility tasks such as title generation.  Raises on
    API errors so the caller can decide how to handle them.

    ``model_id`` is the **bare** Gemini slug (e.g.
    ``"gemini-3-flash-preview"``) — the Gemini SDK rejects host-prefixed
    canonical IDs.  When ``None``, falls back to the first Gemini catalog
    entry's bare slug (the call goes through the Gemini SDK, so it must be
    a Gemini model — not just the first catalog entry overall).
    """
    resolved_model_id = model_id if model_id is not None else _first_gemini_slug()
    client = _get_client()
    # Annotate as the published union so the literal isn't inferred as
    # ``list[Content]`` (which the SDK's overloaded ``contents=`` param
    # type rejects even though it accepts it at runtime).
    contents: list[types.ContentUnion] = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]
    response = await client.aio.models.generate_content(
        model=resolved_model_id,
        contents=contents,
    )
    return (response.text or "").strip()

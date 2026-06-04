"""Lightweight Gemini helpers for one-off, non-streaming calls."""

from __future__ import annotations

from functools import cache

from google import genai
from google.genai import types

from app.infrastructure.config import settings
from app.providers.catalog import first_catalog_model


@cache
def _get_client() -> genai.Client:
    """Return a shared Gemini client, creating it on first call."""
    return genai.Client(api_key=settings.google_api_key)


async def generate_text_once(prompt: str, model_id: str | None = None) -> str:
    """Send a single prompt to Gemini and return the text response.

    Used for short utility tasks such as title generation.  Raises on
    API errors so the caller can decide how to handle them.

    ``model_id`` is the **bare** Gemini slug (e.g.
    ``"gemini-3-flash-preview"``) — the Gemini SDK rejects host-prefixed
    canonical IDs.  When ``None``, falls back to the first catalog
    entry's bare slug so changes to the catalog propagate uniformly.
    """
    resolved_model_id = model_id if model_id is not None else first_catalog_model().model
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

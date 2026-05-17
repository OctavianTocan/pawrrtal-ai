"""Provider factory — resolves a canonical model ID to an :class:`AILLM`.

The factory layer is the only place that reads :mod:`app.core.config`,
keeping the providers themselves config-agnostic and trivially testable
by passing :class:`ClaudeLLMConfig` directly.

Routing is by :class:`Host` rather than by string prefix: every model
ID is parsed into a :class:`ParsedModelId` and dispatched via the
:data:`HOST_TO_PROVIDER` table. Non-canonical IDs raise
:class:`InvalidModelId` — they should already have 422'd at the
Pydantic boundary, so reaching the factory with a bare slug is a
programming error.
"""

from __future__ import annotations

import uuid

from app.core.config import settings

from .base import AILLM
from .claude_provider import ClaudeLLM, ClaudeLLMConfig
from .gemini_provider import GeminiLLM
from .model_id import Host, ParsedModelId, parse_model_id

HOST_TO_PROVIDER: dict[Host, type[AILLM]] = {
    Host.agent_sdk: ClaudeLLM,
    Host.google_ai: GeminiLLM,
}
"""Map of host enum to the concrete provider class that serves it.

Add a new entry when adding a new :class:`Host` — the catalog and
this table must always agree.
"""


def resolve_llm(
    model_id: str | ParsedModelId | None,
    *,
    workspace_id: uuid.UUID | None = None,
) -> AILLM:
    """Return the correct :class:`AILLM` for ``model_id``.

    Args:
        model_id: Canonical wire string (``host:vendor/model``) or a
            pre-parsed identifier. ``None`` defaults to the catalog's
            default model.
        workspace_id: Active workspace UUID, used to resolve
            per-workspace API-key overrides.  ``None`` falls back
            to the global gateway key.

    Returns:
        A provider instance ready to ``stream()``.

    Raises:
        InvalidModelId: If ``model_id`` is a string that doesn't parse.
        KeyError: If ``parsed.host`` has no provider class registered
            (programming error; should not happen at runtime once
            the catalog and ``HOST_TO_PROVIDER`` agree).
    """
    if isinstance(model_id, ParsedModelId):
        parsed = model_id
    else:
        # Local import: avoid a hard import cycle (catalog imports model_id;
        # factory uses catalog only for the default fallback).
        from .catalog import default_model  # noqa: PLC0415 — see comment above

        raw = model_id if model_id is not None else default_model().id
        parsed = parse_model_id(raw)

    provider_cls = HOST_TO_PROVIDER[parsed.host]
    # The table values are typed ``type[AILLM]`` (the streaming protocol),
    # which has no ``__init__`` contract. Construction is concrete: we
    # narrow back to the real classes here so each gets the args its
    # constructor actually accepts.
    if provider_cls is ClaudeLLM:
        config = ClaudeLLMConfig(
            oauth_token=settings.claude_code_oauth_token or None,
        )
        return ClaudeLLM(parsed.model, config=config, workspace_id=workspace_id)
    if provider_cls is GeminiLLM:
        return GeminiLLM(parsed.model, workspace_id=workspace_id)
    raise KeyError(f"no provider class registered for host {parsed.host!r}")

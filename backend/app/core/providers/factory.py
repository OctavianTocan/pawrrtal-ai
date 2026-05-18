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
from pathlib import Path

from app.core.config import settings

from .base import AILLM
from .claude_provider import ClaudeLLM, ClaudeLLMConfig
from .gemini_provider import GeminiLLM
from .litellm_provider import LiteLLMLLM
from .model_id import Host, ParsedModelId, parse_model_id
from .xai_provider import XaiLLM

HOST_TO_PROVIDER: dict[Host, type[AILLM]] = {
    Host.agent_sdk: ClaudeLLM,
    Host.google_ai: GeminiLLM,
    Host.litellm: LiteLLMLLM,
    Host.xai: XaiLLM,
}
"""Map of host enum to the concrete provider class that serves it.

Add a new entry when adding a new :class:`Host` — the catalog and
this table must always agree.
"""


def resolve_llm(
    model_id: str | ParsedModelId | None,
    *,
    workspace_id: uuid.UUID | None = None,
    workspace_root: Path | None = None,
) -> AILLM:
    """Return the correct :class:`AILLM` for ``model_id``.

    Args:
        model_id: Canonical wire string (``host:vendor/model``) or a
            pre-parsed identifier. ``None`` defaults to the catalog's
            default model.
        workspace_id: Active workspace UUID, used to resolve
            per-workspace API-key overrides.  ``None`` falls back
            to the global gateway key.
        workspace_root: The caller's per-user workspace directory. When
            supplied, the Claude SDK subprocess runs with this as its
            ``cwd`` so its transcript files land under the workspace
            (not the backend process directory). ``None`` leaves
            ``cwd`` unset for back-compat with non-chat callers
            (LCM jobs, event-bus handlers) that don't have a
            workspace in scope — those paths still rely on
            ``setting_sources=[]`` in the provider to keep filesystem
            sources off.

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
            cwd=str(workspace_root) if workspace_root is not None else None,
        )
        return ClaudeLLM(parsed.model, config=config, workspace_id=workspace_id)
    if provider_cls is GeminiLLM:
        return GeminiLLM(parsed.model, workspace_id=workspace_id)
    if provider_cls is XaiLLM:
        return XaiLLM(parsed.model, workspace_id=workspace_id)
    if provider_cls is LiteLLMLLM:
        # LiteLLM is multi-vendor — the parsed vendor selects which
        # API-key workspace name to resolve and which LiteLLM provider
        # prefix to prepend at request time.
        return LiteLLMLLM(parsed.model, parsed.vendor, workspace_id=workspace_id)
    raise KeyError(f"no provider class registered for host {parsed.host!r}")

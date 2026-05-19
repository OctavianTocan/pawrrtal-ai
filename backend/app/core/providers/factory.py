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

from pathlib import Path

from app.core.config import settings

from .base import AILLM
from .claude_provider import ClaudeLLM, ClaudeLLMConfig
from .gemini_provider import GeminiLLM
from .litellm_provider import LiteLLMLLM
from .model_id import Host, ParsedModelId, parse_model_id
from .opencode_go_provider import OpencodeGoLLM, OpencodeGoLLMConfig
from .xai_provider import XaiLLM

HOST_TO_PROVIDER: dict[Host, type[AILLM]] = {
    Host.agent_sdk: ClaudeLLM,
    Host.google_ai: GeminiLLM,
    Host.litellm: LiteLLMLLM,
    Host.opencode_go: OpencodeGoLLM,
    Host.xai: XaiLLM,
}
"""Map of host enum to the concrete provider class that serves it.

Add a new entry when adding a new :class:`Host` — the catalog and
this table must always agree.
"""


def resolve_llm(
    model_id: str | ParsedModelId | None,
    *,
    workspace_root: Path | None = None,
) -> AILLM:
    """Return the correct :class:`AILLM` for ``model_id``.

    Args:
        model_id: Canonical wire string (``host:vendor/model``) or a
            pre-parsed identifier. ``None`` defaults to the catalog's
            default model.
        workspace_root: Absolute path from the ``workspaces.path`` DB
            column. Used to resolve per-workspace API-key overrides via
            the encrypted ``{workspace_root}/.env`` file. Also serves
            as ``cwd`` for the Claude SDK subprocess so its transcript
            files land under the workspace. ``None`` leaves both
            behaviours unset for back-compat with non-chat callers
            (LCM jobs, event-bus handlers) that don't have a workspace
            in scope.

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
        return ClaudeLLM(parsed.model, config=config, workspace_root=workspace_root)
    if provider_cls is GeminiLLM:
        return GeminiLLM(parsed.model, workspace_root=workspace_root)
    if provider_cls is XaiLLM:
        return XaiLLM(parsed.model, workspace_root=workspace_root)
    if provider_cls is LiteLLMLLM:
        return LiteLLMLLM(parsed.model, parsed.vendor, workspace_root=workspace_root)
    if provider_cls is OpencodeGoLLM:
        return _build_opencode_go(parsed, workspace_root)
    raise KeyError(f"no provider class registered for host {parsed.host!r}")


def _build_opencode_go(parsed: ParsedModelId, workspace_root: Path | None) -> OpencodeGoLLM:
    """Construct an ``OpencodeGoLLM`` with rates pulled from the catalog.

    The provider stays catalog-agnostic by accepting per-model rates +
    base URL via :class:`OpencodeGoLLMConfig`; the factory is the one
    place that crosses the catalog/provider boundary. Raising
    ``UnknownModelId`` here surfaces a clean 422 to the caller for
    ``opencode-go:<vendor>/<unknown>`` strings that parsed but aren't
    in the catalog.
    """
    # Local import: prevents the import cycle catalog→model_id→factory
    # by matching the pattern already used for ``default_model``.
    from .catalog import find  # noqa: PLC0415

    entry = find(parsed)
    if entry is None:
        from .model_id import UnknownModelId  # noqa: PLC0415

        raise UnknownModelId(f"model not in catalog: {parsed.id}")
    config = OpencodeGoLLMConfig(
        cost_per_mtok_in_usd=entry.cost_per_mtok_in_usd,
        cost_per_mtok_out_usd=entry.cost_per_mtok_out_usd,
        base_url=settings.opencode_go_base_url,
    )
    return OpencodeGoLLM(parsed.model, config=config, workspace_root=workspace_root)

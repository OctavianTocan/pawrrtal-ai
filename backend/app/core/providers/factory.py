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

from app.core.config import settings as settings  # noqa: PLC0414

from .base import AILLM
from .claude_provider import ClaudeLLM, ClaudeLLMConfig
from .gemini_cli import GeminiCliLLM
from .gemini_provider import GeminiLLM
from .litellm_provider import LiteLLMLLM
from .model_id import Host, ParsedModelId, parse_model_id
from .opencode_go_provider import OpencodeGoLLM, OpencodeGoLLMConfig
from .xai_provider import XaiLLM

HOST_TO_PROVIDER: dict[Host, type[AILLM]] = {
    Host.agent_sdk: ClaudeLLM,
    Host.gemini_cli: GeminiCliLLM,
    Host.google_ai: GeminiLLM,
    Host.litellm: LiteLLMLLM,
    Host.opencode_go: OpencodeGoLLM,
    Host.xai: XaiLLM,
}
"""Map of host enum to the concrete provider class that serves it.

Add a new entry when adding a new :class:`Host` — the catalog and
this table must always agree.
"""


def host_authenticated(host: Host) -> bool:
    """Return whether the deployment has credentials wired for ``host``.

    Drives the "only show authenticated providers" filter on the
    ``/api/v1/models`` endpoint (issue #370) so users don't see
    catalog entries they can't actually pick. The check is
    intentionally cheap and stable per-process — :data:`settings`
    is read once at boot, so this function can be called freely
    inside hot paths without touching disk.

    Args:
        host: The :class:`Host` enum value to gate.

    Returns:
        ``True`` when a credential / binary required to drive the
        host is present, ``False`` otherwise.

    Mapping:

    * ``agent_sdk`` (Claude): non-empty ``claude_code_oauth_token``.
    * ``gemini_cli``: the ``gemini`` binary is on ``PATH`` (probed
      via :func:`is_gemini_cli_available`).
    * ``google_ai`` (native Gemini): ``google_api_key`` non-empty.
      ``Settings`` marks the field as required so the value is always
      populated at runtime, but the gate stays uniform with the other
      key-driven hosts rather than carrying a special case.
    * ``litellm``: ``openai_api_key`` non-empty. LiteLLM in this
      catalog only routes OpenAI models, so the OpenAI key is the
      single credential we need.
    * ``opencode_go``: ``opencode_api_key`` non-empty.
    * ``xai``: ``xai_api_key`` non-empty.

    Add a new branch when introducing a new :class:`Host`.
    """
    if host is Host.gemini_cli:
        # Local import: ``gemini_cli`` imports the agent loop which
        # would re-enter the factory module on a top-level import.
        from .gemini_cli import is_gemini_cli_available  # noqa: PLC0415

        return is_gemini_cli_available()
    # Other hosts gate purely on a ``settings.*`` credential. The
    # ``host → attribute`` mapping is a flat dict so adding a host
    # costs one line of data rather than one branch of control flow,
    # and it keeps the function under ruff's ``PLR0911`` return-count
    # budget.
    credential_attr_by_host: dict[Host, str] = {
        Host.agent_sdk: "claude_code_oauth_token",
        Host.google_ai: "google_api_key",
        Host.litellm: "openai_api_key",
        Host.opencode_go: "opencode_api_key",
        Host.xai: "xai_api_key",
    }
    attr = credential_attr_by_host.get(host)
    if attr is None:
        return False
    return bool(getattr(settings, attr))


# Module-import-time exhaustiveness check — converts the "every
# ``Host`` member must have a provider class" invariant from an
# implicit runtime ``KeyError`` in :func:`resolve_llm` into a clear
# import-time ``ValueError`` next to the table itself.
_missing_hosts = set(Host) - set(HOST_TO_PROVIDER)
if _missing_hosts:
    raise ValueError(f"HOST_TO_PROVIDER missing entries for: {_missing_hosts}")


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
    if provider_cls is GeminiCliLLM:
        return GeminiCliLLM(parsed.model, workspace_root=workspace_root)
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

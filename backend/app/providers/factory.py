"""Provider factory — resolves a canonical model ID to an :class:`AILLM`.

The factory layer is the only place that reads :mod:`app.infrastructure.config`,
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

import inspect
from pathlib import Path

from app.infrastructure.config import settings as settings  # noqa: PLC0414

from .agy_api import AgyApiLLM
from .base import AILLM
from .claude import ClaudeLLM, ClaudeLLMConfig
from .gemini_cli import GeminiCliLLM
from .litellm_provider import LiteLLMLLM
from .model_id import Host, InvalidModelId, ParsedModelId, parse_model_id
from .opencode_go import OpencodeGoLLM, OpencodeGoLLMConfig
from .xai import XaiLLM


def _load_openai_codex_provider_cls() -> type[AILLM]:
    """Resolve the OpenAICodexProvider class lazily.

    Imported through the package surface (which exposes the symbol
    lazily via ``__getattr__``) so the SDK bootstrap only runs when
    this function is actually called for a Codex model. Eagerly
    importing it at module scope previously poisoned every chat
    turn — including non-Codex hosts — when the codex binary or
    vendored submodule was unavailable (regression: bean
    pawrrtal-t5j8).
    """
    from .openai_codex import OpenAICodexProvider  # noqa: PLC0415

    return OpenAICodexProvider


def _load_gemini_provider_cls() -> type[AILLM]:
    """Resolve the native Gemini provider class lazily."""
    from .gemini import GeminiLLM  # noqa: PLC0415

    return GeminiLLM


HOST_TO_PROVIDER: dict[Host, type[AILLM] | None] = {
    Host.agent_sdk: ClaudeLLM,
    Host.agy_api: AgyApiLLM,
    Host.agy_cli: None,
    Host.gemini_cli: GeminiCliLLM,
    Host.google_ai: None,  # resolved lazily in resolve_llm
    Host.litellm: LiteLLMLLM,
    Host.opencode_go: OpencodeGoLLM,
    Host.xai: XaiLLM,
    Host.openai_codex: None,  # resolved lazily in resolve_llm
}
"""Map of host enum to the concrete provider class that serves it.

Add a new entry when adding a new :class:`Host` — the catalog and
this table must always agree.
"""


# Host → (workspace env-key, settings attribute) used by the picker
# filter (issue #370). The env-key path is what most providers invoke
# at request time via :func:`app.infrastructure.keys.resolve_api_key`.
# Local CLI-derived hosts and xAI are exceptions: AGY API authenticates
# through the local ``agy`` token/project cache, Gemini CLI authenticates
# by binary availability, and xAI workspace OAuth credentials also
# authenticate the host. :func:`host_authenticated` handles those
# branches directly.
# The settings attribute is the fallback when there is no workspace
# context (system callers).
#
# Add a new row when introducing a new :class:`Host` member.
_HOST_AUTH_KEYS: dict[Host, tuple[str, str]] = {
    Host.agent_sdk: ("CLAUDE_CODE_OAUTH_TOKEN", "claude_code_oauth_token"),
    Host.google_ai: ("GEMINI_API_KEY", "google_api_key"),
    Host.litellm: ("OPENAI_API_KEY", "openai_api_key"),
    Host.opencode_go: ("OPENCODE_API_KEY", "opencode_api_key"),
    Host.xai: ("XAI_API_KEY", "xai_api_key"),
    Host.openai_codex: ("OPENAI_CODEX_OAUTH_TOKEN", "openai_codex_oauth_token"),
}

_CODEX_PROVIDER_CACHE: dict[tuple[str, str | None], AILLM] = {}


def host_authenticated(host: Host, *, workspace_root: Path | None = None) -> bool:
    """Return whether ``host`` has credentials reachable for this request.

    Drives the "only show authenticated providers" filter on the
    ``/api/v1/models`` endpoint (issue #370) so users don't see catalog
    entries they can't actually pick.

    When ``workspace_root`` is provided, the gate uses the same
    workspace → settings resolver that every provider invokes at
    request time (:func:`app.infrastructure.keys.resolve_api_key`). This is the
    contract the picker must match: a user who configures
    ``XAI_API_KEY`` in their workspace ``.env`` (the documented path)
    still gets xAI in the picker even when the gateway-global
    ``settings.xai_api_key`` is empty. Without ``workspace_root`` the
    gate falls back to global ``settings`` only, which is the right
    default for callers without a workspace (system bootstrap, audit
    log emitters).

    Mapping:

    * ``agent_sdk`` (Claude): non-empty ``CLAUDE_CODE_OAUTH_TOKEN``.
    * ``agy_api``: local ``agy`` OAuth token + project cache are present.
    * ``gemini_cli``: the ``gemini`` binary is on ``PATH`` (probed
      via :func:`is_gemini_cli_available`). Workspace overrides don't
      apply — the binary is a process-level dependency.
    * ``google_ai`` (native Gemini): non-empty ``GEMINI_API_KEY``.
    * ``litellm``: non-empty ``OPENAI_API_KEY``. LiteLLM in this
      catalog only routes OpenAI models, so the OpenAI key is the
      single credential we need.
    * ``opencode_go``: non-empty ``OPENCODE_API_KEY``.
    * ``xai``: non-empty workspace OAuth access token or ``XAI_API_KEY``.
    * ``openai_codex``: non-empty ``OPENAI_CODEX_OAUTH_TOKEN`` (or valid ~/.codex/auth.json).

    Add a new entry to :data:`_HOST_ENV_KEY` when introducing a new
    :class:`Host`.
    """
    if host in (Host.agy_api, Host.gemini_cli):
        return _local_cli_host_authenticated(host, workspace_root=workspace_root)
    keys = _HOST_AUTH_KEYS.get(host)
    if keys is None:
        return False
    env_key, settings_attr = keys

    if host is Host.openai_codex:
        # Codex auth is primarily file-based (~/.codex/auth.json or $CODEX_HOME
        # written by `codex login`). The SDK binary discovers it automatically.
        # We also support an explicit OPENAI_CODEX_OAUTH_TOKEN override.
        # The picker is permissive (always True) — the provider surfaces a
        # clear error at stream time if no usable auth exists.
        return True

    if workspace_root is not None:
        if host is Host.xai:
            return _xai_workspace_authenticated(workspace_root, env_key)

        # ``resolve_api_key`` already does workspace → settings fallback,
        # so this single call covers both the per-workspace and the
        # global-default paths in one pass.
        from app.infrastructure.keys import resolve_api_key  # noqa: PLC0415

        return bool(resolve_api_key(workspace_root, env_key))
    # No workspace context — gate on the gateway-global setting only.
    return bool(getattr(settings, settings_attr))


def _local_cli_host_authenticated(host: Host, *, workspace_root: Path | None) -> bool:
    """Return whether a local CLI host has the auth/binary state it needs."""
    if host is Host.agy_api:
        from .agy_api import has_agy_api_auth  # noqa: PLC0415

        return has_agy_api_auth(workspace_root)
    # Local import: ``gemini_cli`` imports the agent loop which would
    # re-enter the factory module on a top-level import.
    from .gemini_cli import is_gemini_cli_available  # noqa: PLC0415

    return is_gemini_cli_available()


def _xai_workspace_authenticated(workspace_root: Path, env_key: str) -> bool:
    """Return whether a workspace has xAI OAuth or legacy API-key auth."""
    from app.infrastructure.keys import (  # noqa: PLC0415
        load_workspace_env,
        resolve_api_key,
    )
    from app.providers.xai.credentials import ACCESS_ENV_KEY  # noqa: PLC0415

    env = load_workspace_env(workspace_root)
    if env.get(ACCESS_ENV_KEY, "").strip():
        return True
    return bool(resolve_api_key(workspace_root, env_key))


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
        from .catalog import first_catalog_model  # noqa: PLC0415 — see comment above

        raw = model_id if model_id is not None else first_catalog_model().id
        try:
            parsed = parse_model_id(raw)
        except InvalidModelId as exc:
            from .plugin_provider import resolve_plugin_llm  # noqa: PLC0415

            try:
                return resolve_plugin_llm(raw, workspace_root=workspace_root)
            except InvalidModelId:
                raise exc from None

    provider_cls = HOST_TO_PROVIDER[parsed.host]
    if parsed.host is Host.google_ai and provider_cls is None:
        provider_cls = _load_gemini_provider_cls()
    if parsed.host is Host.openai_codex and provider_cls is None:
        provider_cls = _load_openai_codex_provider_cls()
    if provider_cls is None:
        raise KeyError(f"no provider class registered for host {parsed.host!r}")
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
    if provider_cls is LiteLLMLLM:
        return LiteLLMLLM(parsed.model, parsed.vendor, workspace_root=workspace_root)
    if provider_cls is OpencodeGoLLM:
        return _build_opencode_go(parsed, workspace_root)
    if parsed.host is Host.openai_codex:
        return _resolve_cached_openai_codex_provider(provider_cls, parsed, workspace_root)
    if parsed.host is Host.google_ai or provider_cls in {AgyApiLLM, GeminiCliLLM, XaiLLM}:
        return provider_cls(parsed.model, workspace_root=workspace_root)  # type: ignore[call-arg]
    raise KeyError(f"no provider class registered for host {parsed.host!r}")


def _resolve_cached_openai_codex_provider(
    provider_cls: type[AILLM],
    parsed: ParsedModelId,
    workspace_root: Path | None,
) -> AILLM:
    """Reuse Codex providers so their owned app-server process stays warm."""
    key = (parsed.model, str(workspace_root) if workspace_root is not None else None)
    provider = _CODEX_PROVIDER_CACHE.get(key)
    if provider is None:
        provider = provider_cls(parsed.model, workspace_root=workspace_root)  # type: ignore[call-arg]
        _CODEX_PROVIDER_CACHE[key] = provider
    return provider


async def close_openai_codex_provider_cache() -> None:
    """Close and clear cached Codex providers during application shutdown."""
    providers = list(_CODEX_PROVIDER_CACHE.values())
    _CODEX_PROVIDER_CACHE.clear()
    for provider in providers:
        close_method = getattr(provider, "close", None)
        if close_method is None:
            continue
        result = close_method()
        if inspect.isawaitable(result):
            await result


async def close_provider_caches() -> None:
    """Close all provider-owned process caches."""
    await close_openai_codex_provider_cache()


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
    # by matching the pattern already used for ``first_catalog_model``.
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

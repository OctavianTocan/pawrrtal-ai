"""Auth helpers for the openai_codex provider.

Philosophy (matching the official Python SDK + codex app-server design):

The `Codex()` / `AsyncCodex()` client and the `codex app-server` binary it
spawns are deliberately designed to own the standard Codex authentication
state written by `codex login` (or the official desktop app):

    ~/.codex/auth.json
    $CODEX_HOME/auth.json

For normal Pawrrtal usage (chat turns, agents, tool use) you do **not** pass
OAuth tokens at construction time. The binary finds and refreshes tokens on
its own using the well-known location.

This module therefore provides only a **thin, minimal** surface:

- `resolve_openai_codex_auth(...)` — returns an explicit override token when
  the caller (usually the legacy image-gen path or a workspace .env) has
  supplied `OPENAI_CODEX_OAUTH_TOKEN`. This is the *only* case where we still
  need to deal with raw tokens.

- `build_app_server_config(...)` — produces an `AppServerConfig` that
  respects per-workspace overrides when present, while staying out of the
  way for the common "just use whatever the user has logged in with" case.

Heavy manual refresh logic, JWT parsing, and single-use refresh token locking
have been removed from this layer. If a future path genuinely needs direct
token manipulation, it should live in the legacy image-gen plugin, not here.

See Also:
- The official SDK docs (sdk/python/docs/)
- `codex login` and the standard auth.json format.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OpenAICodexAuthError(RuntimeError):
    """Raised when no usable Codex auth can be resolved for an override path."""


def resolve_openai_codex_auth(
    *,
    workspace_root: Path | None = None,
    override: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve an *explicit override* Codex OAuth token when one is supplied.

    This is **not** the primary auth path for the first-class provider.

    Resolution order for overrides (highest to lowest):
    1. Explicit `override` argument (most commonly `OPENAI_CODEX_OAUTH_TOKEN`
       from a workspace .env or settings).
    2. (Future) per-workspace auth file under workspace_root/.codex/auth.json.

    Returns:
        (access_token_or_None, chatgpt_account_id_or_None)

    The normal, recommended path for chat and agents is to call
    `Codex()` / `AsyncCodex()` with no special auth configuration and let
    the app-server binary use the user's standard `~/.codex/auth.json`.

    This function is primarily kept for the legacy image-generation plugin
    and for users who need to inject a different identity per workspace.
    """
    if override:
        logger.debug("openai_codex.auth: using explicit override token")
        # We no longer do JWT decoding here for the normal case.
        # Callers that still need the account id can decode it themselves
        # (the legacy image-gen path does this in a couple of places).
        return override, None

    # Future: check for a workspace-scoped auth.json under
    # workspace_root / ".codex" / "auth.json" and return it if present.
    # For v1 we keep the surface minimal and let the binary own the default.

    if workspace_root:
        ws_auth = workspace_root / ".codex" / "auth.json"
        if ws_auth.exists():
            logger.debug(
                "openai_codex.auth: workspace auth file exists at %s (not yet wired)", ws_auth
            )
            # Placeholder for future per-workspace auth support.
            # For now we fall through and let the normal SDK path win.

    # No override present — the caller should simply use the default
    # Codex() / AsyncCodex() behavior.
    return None, None


def build_app_server_config(
    *,
    workspace_root: Path | None = None,
    codex_bin: str | Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an AppServerConfig dict suitable for the official openai_codex SDK.

    For the common case (no per-workspace override) you can simply do:

        config = AppServerConfig(codex_bin=..., cwd=...)
        async with AsyncCodex(config=config) as codex:
            ...

    When a workspace supplies `OPENAI_CODEX_OAUTH_TOKEN`, this helper will
    (in a future refinement) arrange for the app-server process to see that
    identity instead of (or in addition to) the user's global login.

    Current minimal behavior:
    - Passes through `codex_bin` if given.
    - Respects an explicit `OPENAI_CODEX_OAUTH_TOKEN` by returning it in a
      conventional "override" key that the provider implementation can use
      to set `CODEX_HOME` or a temp auth file before launching the binary.
    - Otherwise returns a plain config that lets the SDK do the right thing.

    The return value is a plain dict today (matching the style used elsewhere
    in Pawrrtal). Once we are fully on the real SDK surface we can return a
    real `AppServerConfig` instance.
    """
    override_token, _ = resolve_openai_codex_auth(
        workspace_root=workspace_root,
        override=os.environ.get("OPENAI_CODEX_OAUTH_TOKEN"),
    )

    cfg: dict[str, Any] = {}

    if codex_bin:
        cfg["codex_bin"] = str(codex_bin)
    else:
        # Development convenience: try to auto-discover a built binary from the
        # vendored Codex submodule (backend/vendor/codex). This lets developers
        # use the provider without having the published `openai-codex-cli-bin`
        # wheel installed. Lazy import: `_vendor` mutates sys.path on first
        # call, and we only want that side-effect on the auth path that
        # actually needs a discovered binary.
        from . import _vendor as _codex_vendor  # noqa: PLC0415

        discovered = _codex_vendor.discover_vendored_codex_bin()
        if discovered:
            cfg["codex_bin"] = str(discovered)

    if extra_env:
        cfg["env"] = dict(extra_env)

    if override_token:
        # Mark that an override is present. The actual provider implementation
        # will decide the best way to surface it to the app-server process
        # (temp auth dir + CODEX_HOME, env injection, or login helper call).
        cfg["_openai_codex_override_token"] = override_token
        logger.debug("openai_codex.auth: AppServerConfig will carry an override token")

    return cfg


# Backwards-compat alias used by some older test / plugin code during the
# transition period. New code should call the functions above directly.
resolve_codex_oauth_token = resolve_openai_codex_auth

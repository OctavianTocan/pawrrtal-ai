"""Per-workspace environment variable resolution.

A workspace `.env` file is encrypted at rest under
``{settings.workspace_base_dir}/{workspace_id}/.env``.  Users supply their own
provider keys (e.g. their own ``GEMINI_API_KEY``) without ever editing the
server-wide global ``.env``.  Keying is per-workspace, not per-user — a user
with multiple workspaces configures each independently.  The settings global
remains the gateway-level fallback for any key the workspace doesn't override.

Resolution order for any overridable key:

  1. **Workspace override** — read from the per-workspace encrypted file.
  2. **Gateway global** — fall back to the corresponding ``Settings`` field.
  3. ``None`` — neither is configured.

Step 2 is performed inside :func:`resolve_api_key` itself, so callers
should NEVER write ``resolve_api_key(...) or settings.x_api_key`` — the
``or`` clause is unreachable dead code that diverges if the settings
mapping is ever extended.

This module lives at ``app.core.keys`` (not ``app.core.providers.keys``)
because it is a cross-cutting helper imported by HTTP routes, tools, and
agent factories — none of which are providers.  ``providers/`` is
reserved for SDK-specific bridges (see
``.claude/rules/architecture/no-tools-in-providers.md``).

Note on the historical user-keyed layout (prior to the workspace_id
migration): old ``{workspace_base_dir}/{user_id}/.env`` files are moved to
``{workspace_base_dir}/{default_workspace_id}/.env`` by
:func:`migrate_user_keyed_env_files` on application startup.  After
migration the source file is renamed with a ``.migrated-<timestamp>``
suffix rather than deleted, so the move is reversible.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


# Public allowlist of overridable env keys. The HTTP layer (workspace_env.py)
# rejects anything not in this set with HTTP 400. Keep this in sync with the
# frontend's `WORKSPACE_ENV_KEY_IDS` in
# `frontend/features/settings/workspace-env/use-workspace-env.ts`.
OVERRIDABLE_KEYS: frozenset[str] = frozenset(
    {
        "GEMINI_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "EXA_API_KEY",
        "XAI_API_KEY",
        "OPENAI_CODEX_OAUTH_TOKEN",
        # Notion plugin (see backend/app/integrations/notion/).  The plugin
        # registry declares the same key via its EnvKeySpec; this central
        # allowlist remains the source of truth for the HTTP layer.
        "NOTION_API_KEY",
    }
)


# Maps the workspace-facing env-var name (the canonical name the user types
# in their browser) to the corresponding `Settings` field name on the gateway
# global config. Order doesn't matter; the lookup is by key.
_SETTINGS_ATTR_MAP: dict[str, str] = {
    "GEMINI_API_KEY": "google_api_key",
    "CLAUDE_CODE_OAUTH_TOKEN": "claude_code_oauth_token",
    "EXA_API_KEY": "exa_api_key",
    "XAI_API_KEY": "xai_api_key",
    # OPENAI_CODEX_OAUTH_TOKEN intentionally absent — workspace-only, no
    # global settings fallback.  resolve_api_key() returns None for keys
    # missing from this map after the workspace lookup fails.
}


# Workspace .env files do not allow newline characters in values: we serialise
# one key per line as `KEY=value`, and a value containing a newline would
# split into a second key=value pair on parse. The `WorkspaceEnvVars` model
# in `workspace_env.py` validates incoming values against this pattern; the
# constant lives here so backend tests can import it directly.
VALUE_FORBIDDEN_CHARS = re.compile(r"[\r\n]")


def _workspace_env_path(workspace_id: uuid.UUID) -> Path:
    """Return the absolute path to a workspace's encrypted ``.env`` file.

    Computed on every call so that test code can monkeypatch
    ``settings.workspace_base_dir`` without restarting the import graph.

    The path matches the canonical workspace directory shape produced by
    :func:`app.core.workspace.seed_workspace` — i.e. the env file is a
    sibling of ``AGENTS.md`` / ``SOUL.md`` and lives inside the workspace
    root.  This keeps the per-workspace state self-contained so a single
    rsync of the workspace directory moves the agent state and its
    credentials together.
    """
    return Path(settings.workspace_base_dir) / str(workspace_id) / ".env"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Return a process-wide Fernet instance.

    Cached because constructing a Fernet re-parses + re-validates the
    base64-encoded 32-byte key. The key is loaded from `settings` at boot
    and cannot change at runtime, so a single instance is correct.
    """
    return Fernet(settings.workspace_encryption_key.encode())


def _parse_env_lines(plaintext: str) -> dict[str, str]:
    """Parse decrypted plaintext into a {KEY: value} mapping.

    Skips empty lines and `#`-prefixed comment lines. Values are trimmed
    of surrounding whitespace.
    """
    env: dict[str, str] = {}
    for raw in plaintext.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _serialize_env_lines(env: dict[str, str]) -> str:
    """Serialise a {KEY: value} mapping into the file's plaintext form.

    Empty-string values are dropped: the user-facing semantic of "clear this
    field and Save" is "use the gateway default", which is what an absent
    key produces. Keeping the empty entry in the file would be ambiguous.
    """
    lines = [f"{k}={v}" for k, v in env.items() if v != ""]
    return "\n".join(lines)


def _quarantine_corrupt_file(path: Path) -> None:
    """Rename an unreadable .env file out of the way and log a WARNING.

    Decryption can fail when:
      * The encryption key was rotated since the file was written.
      * The file is partially written or corrupted on disk.
    Either way, blocking every request for that user is worse than letting
    them re-enter their keys, so we move the bad file aside and continue.
    """
    suffix = f".corrupt-{int(time.time())}"
    target = path.with_name(path.name + suffix)
    try:
        path.rename(target)
        logger.warning(
            "workspace_env: quarantined corrupt encrypted file at %s -> %s",
            path,
            target,
        )
    except OSError as err:
        # Don't escalate — the read path will return {} either way; the
        # next save will overwrite the file.
        logger.warning(
            "workspace_env: failed to quarantine corrupt file at %s: %s",
            path,
            err,
        )


def load_workspace_env(workspace_id: uuid.UUID) -> dict[str, str]:
    """Decrypt and parse the workspace's ``.env`` file.

    Returns an empty dict when:
      * No file exists yet (first-time workspace).
      * The file exists but cannot be decrypted (corrupt or key-rotated);
        in this case the bad file is quarantined to a sibling path and a
        WARNING is logged.
    """
    path = _workspace_env_path(workspace_id)
    if not path.exists():
        return {}
    try:
        plaintext = _fernet().decrypt(path.read_bytes()).decode()
    except InvalidToken:
        _quarantine_corrupt_file(path)
        return {}
    return _parse_env_lines(plaintext)


def save_workspace_env(workspace_id: uuid.UUID, env: dict[str, str]) -> None:
    """Encrypt and persist the workspace's ``.env`` file.

    Permissions: the workspace directory is created with mode 0o700 and
    the file is chmod'd to 0o600 after write so no other OS user can read
    it. This is defence-in-depth — the file contents are already encrypted.

    Empty-string values are stripped during serialisation; saving an empty
    string for a key is the documented way for a user to "clear" the
    override and fall back to the gateway default.
    """
    path = _workspace_env_path(workspace_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    plaintext = _serialize_env_lines(env)
    ciphertext = _fernet().encrypt(plaintext.encode())
    path.write_bytes(ciphertext)
    path.chmod(0o600)


def resolve_api_key(workspace_id: uuid.UUID, workspace_key: str) -> str | None:
    """Resolve an env key for the given workspace with workspace → settings fallback.

    Args:
        workspace_id: The active workspace UUID. Used to locate the
            encrypted ``.env`` file.
        workspace_key: One of :data:`OVERRIDABLE_KEYS`, e.g.
            ``"GEMINI_API_KEY"``.

    Returns:
        The first non-empty value found, in this order:
          1. The workspace's override.
          2. The corresponding ``Settings`` field
             (``_SETTINGS_ATTR_MAP[workspace_key]``).
          3. ``None`` if neither is configured.

    Callers MUST NOT write ``resolve_api_key(...) or settings.x``. The
    ``or`` clause is unreachable: this function already performs the
    settings fallback via :data:`_SETTINGS_ATTR_MAP`. A second fallback
    at the call site is dead code that drifts when the map is extended.
    """
    workspace = load_workspace_env(workspace_id)
    override = workspace.get(workspace_key)
    if override:
        return override
    settings_attr = _SETTINGS_ATTR_MAP.get(workspace_key)
    if settings_attr is None:
        return None
    value = getattr(settings, settings_attr, None)
    return value or None


# ---------------------------------------------------------------------------
# One-time migration: user-keyed → workspace-keyed
# ---------------------------------------------------------------------------


def migrate_user_keyed_env_file(
    *,
    user_id: uuid.UUID,
    default_workspace_id: uuid.UUID,
) -> bool:
    """Move a legacy ``{base}/{user_id}/.env`` to ``{base}/{workspace_id}/.env``.

    Returns ``True`` when a file was migrated, ``False`` when there was
    nothing to do. Idempotent — calling again after a successful run is
    a no-op (the source no longer exists).

    The migration is non-destructive: after copying the encrypted bytes
    to the new path the source file is renamed to
    ``.env.migrated-<timestamp>`` rather than deleted. Operators can
    recover the original value by renaming the suffix back.

    Args:
        user_id: The user whose legacy env file we're migrating.
        default_workspace_id: The workspace that inherits the user's
            keys.  Only the default workspace is seeded — secondary
            workspaces start blank, on the principle that "isolated
            workspace" means a fresh credentials slate.
    """
    base = Path(settings.workspace_base_dir)
    src = base / str(user_id) / ".env"
    if not src.exists():
        return False

    dst = base / str(default_workspace_id) / ".env"
    if dst.exists():
        # Already-migrated workspace; quarantine the legacy source so a
        # second run cannot accidentally overwrite the newer file.
        _quarantine_corrupt_file(src)
        return False

    dst.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    dst.chmod(0o600)

    migrated_suffix = f".migrated-{int(time.time())}"
    src.rename(src.with_name(src.name + migrated_suffix))
    logger.info(
        "workspace_env: migrated user-keyed env file user_id=%s -> workspace_id=%s",
        user_id,
        default_workspace_id,
    )
    return True

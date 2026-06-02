"""Local Antigravity auth/cache helpers.

This module intentionally never logs token values. The direct API path
reuses the token file written by ``agy`` and treats refresh/login as the
CLI's job until we have explicit approval to own that OAuth flow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_AGY_CONFIG_DIR = Path.home() / ".gemini" / "antigravity-cli"
_TOKEN_PATH = _AGY_CONFIG_DIR / "antigravity-oauth-token"
_PROJECTS_PATH = _AGY_CONFIG_DIR / "cache" / "projects.json"


class AgyApiAuthError(RuntimeError):
    """Raised when local ``agy`` auth/cache state is not usable."""


@dataclass(frozen=True, slots=True)
class AgyApiAuth:
    """Usable local Antigravity API auth material."""

    access_token: str
    project_id: str


def has_agy_api_auth(workspace_root: Path | None = None) -> bool:
    """Return whether local Antigravity auth exists for this workspace."""
    try:
        load_agy_api_auth(workspace_root)
    except AgyApiAuthError:
        return False
    return True


def load_agy_api_auth(workspace_root: Path | None = None) -> AgyApiAuth:
    """Load a non-expired ``agy`` token and cached project id."""
    raw_token = _load_json(_TOKEN_PATH, "Antigravity OAuth token")
    if not isinstance(raw_token, dict):
        raise AgyApiAuthError("Antigravity token file is malformed.")
    token: dict[str, object] = dict(raw_token)
    raw_token_body = token.get("token")
    if not isinstance(raw_token_body, dict):
        raise AgyApiAuthError("Antigravity token file is malformed.")
    token_body: dict[str, object] = dict(raw_token_body)

    expiry = token_body.get("expiry")
    if isinstance(expiry, str) and _is_expired(expiry):
        raise AgyApiAuthError(
            "Antigravity access token is expired; run agy once in this workspace "
            "so the CLI refreshes its token."
        )

    access_token = token_body.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise AgyApiAuthError("Antigravity access token is missing.")

    return AgyApiAuth(
        access_token=access_token,
        project_id=_load_project_id(workspace_root),
    )


def _load_project_id(workspace_root: Path | None) -> str:
    projects = _load_json(_PROJECTS_PATH, "Antigravity project cache")
    if not isinstance(projects, dict) or not projects:
        raise AgyApiAuthError("Antigravity project cache is empty; run agy once in the workspace.")
    if workspace_root is not None:
        project_id = projects.get(str(workspace_root))
        if isinstance(project_id, str) and project_id:
            return project_id
    first_project = next((value for value in projects.values() if isinstance(value, str)), "")
    if first_project:
        return first_project
    raise AgyApiAuthError("Antigravity project cache has no project id.")


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgyApiAuthError(f"{label} not found at {path}.") from exc
    except json.JSONDecodeError as exc:
        raise AgyApiAuthError(f"{label} is not valid JSON.") from exc


def _is_expired(expiry: str) -> bool:
    normalized = _normalize_rfc3339(expiry)
    try:
        expires_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AgyApiAuthError("Antigravity token expiry is malformed.") from exc
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)


def _normalize_rfc3339(value: str) -> str:
    """Normalize Go-style RFC3339Nano timestamps for ``fromisoformat``."""
    suffix = "+00:00" if value.endswith("Z") else ""
    body = value[:-1] if suffix else value
    if "." not in body:
        return body + suffix
    head, tail = body.split(".", 1)
    offset = ""
    for marker in ("+", "-"):
        if marker in tail:
            fraction, offset_tail = tail.split(marker, 1)
            offset = marker + offset_tail
            break
    else:
        fraction = tail
    return f"{head}.{fraction[:6]}{offset or suffix}"

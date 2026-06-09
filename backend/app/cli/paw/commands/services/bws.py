"""Bitwarden Secrets Manager loading for service targets."""

from __future__ import annotations

import json
import os
import re
import subprocess

from app.cli.paw.commands.services.targets import ServiceTarget
from app.cli.paw.errors import LocalError, PawError

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXIT_BWS_AUTH = 4
EXIT_BWS_EXTERNAL = 5


class BitwardenAuthError(PawError):
    """Bitwarden access is missing or rejected."""

    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=EXIT_BWS_AUTH, hint=hint)


class BitwardenExternalError(PawError):
    """The bws process failed."""

    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=EXIT_BWS_EXTERNAL, hint=hint)


def load_secret_environment(target: ServiceTarget) -> dict[str, str]:
    """Load and merge Bitwarden secrets for a target."""
    if not os.environ.get("BWS_ACCESS_TOKEN"):
        raise BitwardenAuthError(
            "BWS_ACCESS_TOKEN is not set.",
            hint="Load it from the root-owned service env file before starting Pawrrtal.",
        )
    env: dict[str, str] = {}
    if target.bws_shared_project_id:
        shared = _load_project_secrets(target.bws_shared_project_id)
        env.update(_filter_allowed(shared, target.shared_keys))
    if not target.bws_project_id:
        raise LocalError(
            f"No Bitwarden project configured for target {target.name}.",
            hint="Set bws_project_id in /etc/pawrrtal/services.toml.",
        )
    env.update(_load_project_secrets(target.bws_project_id))
    _validate_required(target, env)
    return env


def secret_check_payload(target: ServiceTarget) -> dict[str, object]:
    """Return a metadata-only check result for a target."""
    secrets = load_secret_environment(target)
    return {
        "target": target.name,
        "project_id": target.bws_project_id,
        "shared_project_id": target.bws_shared_project_id,
        "loaded_keys": sorted(secrets),
        "required_keys": list(target.required_secrets),
        "missing_required_keys": [key for key in target.required_secrets if not secrets.get(key)],
    }


def _load_project_secrets(project_id: str) -> dict[str, str]:
    """Load one Bitwarden project without printing secret values."""
    result = _run_bws(["bws", "secret", "list", "--project-id", project_id, "--output", "json"])
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BitwardenExternalError(
            f"Bitwarden returned invalid JSON for project {project_id}.",
            hint="Run `bws secret list --project-id <id> --output json` manually.",
        ) from exc
    if not isinstance(items, list):
        raise BitwardenExternalError(
            f"Bitwarden returned an unexpected payload for project {project_id}.",
            hint="Expected a JSON array of secrets.",
        )
    secrets: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("name")
        value = item.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if not ENV_NAME_RE.match(key):
            raise LocalError(
                f"Invalid Bitwarden secret key for environment injection: {key}",
                hint="Use POSIX-style environment names such as DATABASE_URL.",
            )
        secrets[key] = value
    return secrets


def _filter_allowed(secrets: dict[str, str], allowed_keys: tuple[str, ...]) -> dict[str, str]:
    """Keep only allowlisted shared secrets."""
    allowed = set(allowed_keys)
    return {key: value for key, value in secrets.items() if key in allowed}


def _validate_required(target: ServiceTarget, secrets: dict[str, str]) -> None:
    """Fail fast when a required secret is absent or empty."""
    missing = [key for key in target.required_secrets if not secrets.get(key)]
    if missing:
        missing_text = ", ".join(missing)
        raise LocalError(
            f"Missing required Bitwarden secrets for target {target.name}: {missing_text}",
            hint=f"Add them to the {target.name} Bitwarden project or choose another target.",
        )


def _run_bws(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run bws and normalize auth/external failures."""
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise BitwardenExternalError(
            "`bws` not found on PATH.",
            hint="Install Bitwarden Secrets Manager CLI on this host.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        lowered = output.lower()
        if "unauthorized" in lowered or "access token" in lowered or "forbidden" in lowered:
            raise BitwardenAuthError(
                "Bitwarden rejected the configured access token.",
                hint="Check BWS_ACCESS_TOKEN and project access for this machine account.",
            ) from exc
        raise BitwardenExternalError(
            f"`{' '.join(args[:3])} ...` failed with exit code {exc.returncode}.",
            hint=output or None,
        ) from exc

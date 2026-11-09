"""Target configuration for ``paw services``."""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from app.cli.paw.commands.project.state import repo_root
from app.cli.paw.errors import LocalError

DEFAULT_TARGET = "prod"
DEFAULT_CONFIG_PATH = Path("/etc/pawrrtal/services.toml")
DEFAULT_BWS_ENV_FILE = Path("/etc/pawrrtal/bws.env")
CONFIG_PATH_ENV = "PAWRRTAL_SERVICES_CONFIG"
TARGET_ENV = "PAWRRTAL_SERVICE_TARGET"
SHARED_KEYS = ("GOOGLE_API_KEY", "EXA_API_KEY", "OPENCODE_API_KEY")
REQUIRED_SECRETS = (
    "DATABASE_URL",
    "AUTH_SECRET",
    "WORKSPACE_ENCRYPTION_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_USERNAME",
)


@dataclass(frozen=True)
class ServiceTarget:
    """Resolved service target used for systemd and Bitwarden launch."""

    name: str
    service_name: str
    workdir: Path
    env: str
    frontend_port: int
    backend_port: int
    bws_project_id: str
    bws_shared_project_id: str
    shared_keys: tuple[str, ...]
    required_secrets: tuple[str, ...]
    environment: dict[str, str]
    public_hostname: str = ""
    enable_dev_login: bool = False

    def payload(self) -> dict[str, Any]:
        """Return a JSON-safe target description without secret values."""
        body = asdict(self)
        body["workdir"] = str(self.workdir)
        return body


@dataclass(frozen=True)
class ServicesConfig:
    """Complete services config."""

    default_target: str
    targets: dict[str, ServiceTarget]


def config_path(value: str | None = None) -> Path:
    """Resolve the services config path from flag, env, or default."""
    raw = value or os.environ.get(CONFIG_PATH_ENV) or str(DEFAULT_CONFIG_PATH)
    return Path(raw).expanduser()


def built_in_targets() -> dict[str, ServiceTarget]:
    """Return built-in prod/dev targets for this checkout."""
    root = repo_root()
    return {
        "prod": ServiceTarget(
            name="prod",
            service_name="pawrrtal.service",
            workdir=root,
            env="prod",
            frontend_port=3000,
            backend_port=8000,
            bws_project_id="",
            bws_shared_project_id="",
            shared_keys=SHARED_KEYS,
            required_secrets=REQUIRED_SECRETS,
            environment={},
        ),
        "dev": ServiceTarget(
            name="dev",
            service_name="pawrrtal-dev.service",
            workdir=root,
            env="dev",
            frontend_port=3100,
            backend_port=8100,
            bws_project_id="",
            bws_shared_project_id="",
            shared_keys=SHARED_KEYS,
            required_secrets=REQUIRED_SECRETS,
            environment={},
        ),
    }


def load_services_config(path: Path | None = None) -> ServicesConfig:
    """Load services config and merge it over built-in targets."""
    resolved_path = path or config_path()
    targets = built_in_targets()
    default_target = DEFAULT_TARGET
    if resolved_path.exists():
        try:
            raw = tomllib.loads(resolved_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise LocalError(
                f"Could not parse services config: {resolved_path}",
                hint=str(exc),
            ) from exc
        default_target = _string_value(raw.get("default_target"), DEFAULT_TARGET)
        targets.update(_parse_targets(raw.get("targets", {}), targets))
    return ServicesConfig(default_target=default_target, targets=targets)


def resolve_target(name: str | None = None, *, path: Path | None = None) -> ServiceTarget:
    """Resolve a target by positional name, env, config default, or built-in default."""
    config = load_services_config(path)
    target_name = _string_value(name, "") or _string_value(os.environ.get(TARGET_ENV), "")
    if not target_name:
        target_name = config.default_target or DEFAULT_TARGET
    target = config.targets.get(target_name)
    if target is None:
        known = ", ".join(sorted(config.targets))
        raise LocalError(
            f"Unknown services target: {target_name}",
            hint=f"Known targets: {known}",
        )
    return target


def save_default_target(target_name: str, *, path: Path | None = None) -> None:
    """Persist the default target in the services config."""
    resolved_path = path or config_path()
    config = load_services_config(resolved_path)
    if target_name not in config.targets:
        known = ", ".join(sorted(config.targets))
        raise LocalError(f"Unknown services target: {target_name}", hint=f"Known targets: {known}")
    existing = resolved_path.read_text(encoding="utf-8") if resolved_path.exists() else ""
    body = _replace_or_prepend_default(existing, target_name)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(body, encoding="utf-8")


def _parse_targets(
    raw_targets: object, defaults: dict[str, ServiceTarget]
) -> dict[str, ServiceTarget]:
    """Parse TOML target tables."""
    if not isinstance(raw_targets, dict):
        raise LocalError("Invalid services config.", hint="The [targets] table must be an object.")
    parsed: dict[str, ServiceTarget] = {}
    for name, raw_target in raw_targets.items():
        if not isinstance(raw_target, dict):
            raise LocalError(
                f"Invalid services target: {name}",
                hint="Each target must be a TOML table.",
            )
        base = defaults.get(name, defaults[DEFAULT_TARGET])
        parsed[name] = replace(
            base,
            name=name,
            service_name=_string_value(raw_target.get("service_name"), base.service_name),
            workdir=Path(_string_value(raw_target.get("workdir"), str(base.workdir))).expanduser(),
            env=_string_value(raw_target.get("env"), base.env),
            frontend_port=_int_value(raw_target.get("frontend_port"), base.frontend_port),
            backend_port=_int_value(raw_target.get("backend_port"), base.backend_port),
            bws_project_id=_string_value(raw_target.get("bws_project_id"), base.bws_project_id),
            bws_shared_project_id=_string_value(
                raw_target.get("bws_shared_project_id"),
                base.bws_shared_project_id,
            ),
            shared_keys=_string_tuple(raw_target.get("shared_keys"), base.shared_keys),
            required_secrets=_string_tuple(
                raw_target.get("required_secrets"),
                base.required_secrets,
            ),
            environment=_environment_dict(raw_target.get("environment"), base.environment),
            public_hostname=_string_value(raw_target.get("public_hostname"), base.public_hostname),
            enable_dev_login=_bool_value(
                raw_target.get("enable_dev_login"),
                base.enable_dev_login,
            ),
        )
    return parsed


def _string_value(value: object, default: str) -> str:
    """Return a stripped string or default for empty/non-string values."""
    if not isinstance(value, str):
        return default
    stripped = value.strip()
    return stripped or default


def _int_value(value: object, default: int) -> int:
    """Return an int config value or default."""
    if isinstance(value, int):
        return value
    return default


def _bool_value(value: object, default: bool) -> bool:
    """Return a bool config value or default."""
    if isinstance(value, bool):
        return value
    return default


def _string_tuple(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    """Return a tuple of non-empty strings."""
    if not isinstance(value, list):
        return default
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _environment_dict(value: object, default: dict[str, str]) -> dict[str, str]:
    """Return target-specific non-secret environment settings."""
    if not isinstance(value, dict):
        return dict(default)
    environment: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(item, bool):
            environment[key.strip()] = "true" if item else "false"
            continue
        if isinstance(item, int | float):
            environment[key.strip()] = str(item)
            continue
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                environment[key.strip()] = stripped
    return environment


def _replace_or_prepend_default(existing: str, target_name: str) -> str:
    """Update or insert the top-level default target setting."""
    line = f'default_target = "{target_name}"'
    lines = existing.splitlines()
    for index, current in enumerate(lines):
        if current.strip().startswith("default_target"):
            lines[index] = line
            return "\n".join(lines) + "\n"
    if not existing.strip():
        return f"{line}\n"
    return f"{line}\n\n{existing.rstrip()}\n"

"""Environment preflight checks for ``paw project`` and ``paw env``."""

from __future__ import annotations

import os
import shutil
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import typer

from app.cli.paw.commands.project.state import DEFAULT_BACKEND_URL, DEFAULT_FRONTEND_URL, repo_root
from app.cli.paw.config import profile_dir
from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    """One automation-friendly environment check result."""

    name: str
    passed: bool
    message: str
    hint: str | None = None


def run_preflight_checks(*, profile: str) -> list[PreflightCheck]:
    """Return all checks required before starting the full local project."""
    cache_root = repo_root() / ".cache"
    return [
        _binary_check("bun"),
        _binary_check("uv"),
        _writable_dir_check("uv_cache_dir_writable", _env_path("UV_CACHE_DIR", cache_root / "uv")),
        _writable_dir_check(
            "xdg_cache_home_writable",
            _env_path("XDG_CACHE_HOME", cache_root / "xdg"),
        ),
        _writable_dir_check("paw_config_dir_writable", profile_dir(profile)),
        _port_available_check("frontend_port_available", DEFAULT_FRONTEND_URL),
        _port_available_check("backend_port_available", DEFAULT_BACKEND_URL),
    ]


def emit_preflight(checks: list[PreflightCheck], *, json_out: bool, plain: bool) -> None:
    """Emit preflight results in the selected output mode."""
    payload = preflight_payload(checks)
    if json_out:
        emit_json(payload)
        return
    if plain:
        emit_plain_rows(
            [
                [
                    check.name,
                    "pass" if check.passed else "fail",
                    check.message,
                    check.hint or "",
                ]
                for check in checks
            ]
        )
        return
    lines = ["preflight: ok" if payload["ok"] else "preflight: failed"]
    for check in checks:
        status = "ok" if check.passed else "fail"
        lines.append(f"{status}\t{check.name}\t{check.message}")
        if check.hint and not check.passed:
            lines.append(f"hint\t{check.hint}")
    emit_human("\n".join(lines))


def preflight_payload(checks: list[PreflightCheck]) -> dict[str, object]:
    """Return the structured preflight payload."""
    return {
        "ok": all(check.passed for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def raise_if_preflight_failed(checks: list[PreflightCheck]) -> None:
    """Raise an actionable local error when any preflight check fails."""
    failures = [check for check in checks if not check.passed]
    if not failures:
        return
    first = failures[0]
    raise LocalError(
        f"Project preflight failed: {first.name}: {first.message}",
        hint=first.hint or "Run `paw project preflight` for details.",
    )


def exit_if_preflight_failed(checks: list[PreflightCheck]) -> None:
    """Exit 1 when any preflight check failed."""
    if not all(check.passed for check in checks):
        raise typer.Exit(code=1)


def _binary_check(binary: str) -> PreflightCheck:
    """Check whether a required binary is on PATH."""
    path = shutil.which(binary)
    if path is None:
        return PreflightCheck(
            name=f"{binary}_available",
            passed=False,
            message=f"`{binary}` not found on PATH.",
            hint=f"Install {binary}, then rerun `paw env check`.",
        )
    return PreflightCheck(name=f"{binary}_available", passed=True, message=path)


def _env_path(name: str, default: Path) -> Path:
    """Resolve an env-controlled path relative to the repo when unset/relative."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    path = Path(raw)
    if path.is_absolute():
        return path
    return repo_root() / path


def _writable_dir_check(name: str, path: Path) -> PreflightCheck:
    """Check that a directory can be created and written."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".paw-write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return PreflightCheck(
            name=name,
            passed=False,
            message=f"{path} is not writable: {exc}",
            hint="Set the related environment variable to a writable directory.",
        )
    return PreflightCheck(name=name, passed=True, message=f"{path} is writable.")


def _port_available_check(name: str, url: str) -> PreflightCheck:
    """Check that the dev URL's port can be bound by the launcher."""
    bind_error = _bind_error(url)
    if bind_error is not None:
        return PreflightCheck(
            name=name,
            passed=False,
            message=f"{url} cannot be bound: {bind_error}",
            hint="Stop the existing dev server or run this in an environment that permits local sockets.",
        )
    return PreflightCheck(name=name, passed=True, message=f"{url} can be bound.")


def _bind_error(url: str) -> str | None:
    """Return a bind error for ``url`` or ``None`` when bind succeeds."""
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port
    if host is None or port is None:
        return "URL has no host or port"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
    except OSError as exc:
        return str(exc)
    return None

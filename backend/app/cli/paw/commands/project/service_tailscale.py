"""Tailscale helpers for the Pawrrtal project service CLI."""

from __future__ import annotations

from typing import Any

from app.cli.paw.commands.project.state import DEFAULT_BACKEND_URL, DEFAULT_FRONTEND_URL

DEFAULT_TAILSCALE_HTTPS_PORT = 443
TAILSCALE_ROUTES = (
    ("/", DEFAULT_FRONTEND_URL),
    ("/api/v1/", f"{DEFAULT_BACKEND_URL}/api/v1/"),
    ("/auth/", f"{DEFAULT_BACKEND_URL}/auth/"),
    ("/users/", f"{DEFAULT_BACKEND_URL}/users/"),
)


def tailscale_self_dns_name(status: dict[str, Any]) -> str | None:
    """Extract the current node's MagicDNS name from ``tailscale status --json``."""
    self_status = status.get("Self")
    if not isinstance(self_status, dict):
        return None
    dns_name = self_status.get("DNSName")
    if not isinstance(dns_name, str):
        return None
    hostname = dns_name.rstrip(".").lower()
    return hostname or None


def tailscale_public_origin(hostname: str | None, port: int) -> str:
    """Return the browser origin for the managed Tailscale profile."""
    if hostname is None:
        return ""
    port_suffix = "" if port == DEFAULT_TAILSCALE_HTTPS_PORT else f":{port}"
    return f"https://{hostname}{port_suffix}"


def tailscale_origin_label(hostname: str, port: int) -> str:
    """Return the Tailscale Serve status origin key for a host and HTTPS port."""
    return f"{hostname}:{port}"


def serve_port_has_config(status: dict[str, Any], *, hostname: str, port: int) -> bool:
    """Return true when the requested Tailscale Serve origin already has handlers."""
    web = status.get("Web")
    if not isinstance(web, dict):
        return False
    origin = web.get(tailscale_origin_label(hostname, port))
    return serve_status_has_config(origin)


def serve_status_has_config(value: object) -> bool:
    """Return true when Tailscale Serve status contains non-empty config."""
    if value in (None, False, "", 0):
        return False
    if isinstance(value, dict):
        return any(serve_status_has_config(child) for child in value.values())
    if isinstance(value, list):
        return any(serve_status_has_config(child) for child in value)
    return True

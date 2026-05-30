"""Gateway-global host authentication checks for the Telegram model picker.

Centralises the mapping from host slugs to their required ``settings``
attribute so that :mod:`model_picker` can filter unauthenticated hosts
without pulling in ``app.infrastructure.config`` directly.
"""

from __future__ import annotations

from app.infrastructure.config import settings

# Host → settings field that must be non-empty for the host to appear in
# the picker (#370). Hosts that don't require a gateway API key
# (``gemini-cli`` uses a local subprocess) are absent from this map and
# always shown.
_HOST_AUTH_SETTING: dict[str, str] = {
    "agent-sdk": "claude_code_oauth_token",
    "google-ai": "google_api_key",
    "litellm": "openai_api_key",
    "opencode-go": "opencode_api_key",
    "xai": "xai_api_key",
}


def is_host_authenticated(host_slug: str) -> bool:
    """Return whether the gateway-global config has the credentials for ``host_slug``.

    Used by the picker to hide hosts whose credentials aren't configured
    so the user doesn't pick a model that will immediately fail. Per-
    workspace overrides aren't consulted here — the picker runs in the
    chat surface (not the workspace), and a host that only some
    workspaces have keys for is still better hidden than shown with a
    failing default. When a workspace lands real per-user picker
    filtering, that work threads workspace_root through this seam.

    Hosts absent from :data:`_HOST_AUTH_SETTING` (e.g. ``gemini-cli``,
    which runs a local subprocess rather than calling out to a managed
    gateway) are always considered authenticated.
    """
    setting_name = _HOST_AUTH_SETTING.get(host_slug)
    if setting_name is None:
        return True
    return bool(getattr(settings, setting_name, "") or "")


__all__ = [
    "is_host_authenticated",
]

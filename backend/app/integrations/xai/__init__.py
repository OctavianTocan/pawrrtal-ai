"""xAI integration surface.

Owns the OAuth device-code flow (#372) and any future xAI-specific
adapters that don't belong inside the provider layer. The provider
itself (``backend/app/core/providers/xai_provider.py``) consumes
this module's :func:`resolve_xai_credentials` to pick between an
OAuth access token and the legacy long-lived ``XAI_API_KEY``.
"""

from app.integrations.xai.credentials import resolve_xai_credentials
from app.integrations.xai.oauth import (
    DeviceCodeGrant,
    DeviceCodeRequest,
    OAuthError,
    poll_for_token,
    refresh_token,
    request_device_code,
)

__all__ = [
    "DeviceCodeGrant",
    "DeviceCodeRequest",
    "OAuthError",
    "poll_for_token",
    "refresh_token",
    "request_device_code",
    "resolve_xai_credentials",
]

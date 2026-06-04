"""Google Chat channel adapter.

Bridges Google Chat (Workspace) to Pawrrtal. Everything provider-specific
(Pub/Sub pull transport, Chat REST send/patch, service-account auth)
lives here; the rest of the codebase stays Google-Chat-agnostic.

Single-user dogfood scope: one Google account auto-links to the
dev-admin via ``GOOGLE_CHAT_DEV_ADMIN_ID`` (no link-code flow). Delivery
is a placeholder message patched once with the final answer.
"""

from app.channels.google_chat.channel import (
    SURFACE_GOOGLE_CHAT,
    GoogleChatChannel,
)
from app.channels.google_chat.ingress import (
    GoogleChatService,
    build_google_chat_service,
    google_chat_lifespan,
)

__all__ = [
    "SURFACE_GOOGLE_CHAT",
    "GoogleChatChannel",
    "GoogleChatService",
    "build_google_chat_service",
    "google_chat_lifespan",
]

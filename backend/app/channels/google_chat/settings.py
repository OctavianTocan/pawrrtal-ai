"""Package-local settings for the Google Chat channel.

These live here rather than on the global
:class:`app.infrastructure.config.Settings` because that class is at the
500-line file budget. pydantic-settings supports composing multiple
``BaseSettings``, so the channel keeps its own config alongside its other
modules (the package-multi-file-features rule). It reads the same
``backend/.env`` + process environment the global settings use, so the
``GOOGLE_CHAT_*`` vars resolve identically in dev and prod.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env — this module sits at backend/app/channels/google_chat/, so
# the backend root is four parents up. Matches the global Settings env_file
# so a single ``.env`` configures every channel.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class GoogleChatSettings(BaseSettings):
    """Service-account + Pub/Sub config for the Google Chat channel."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Path to the Google Cloud service-account JSON used to authenticate
    # Chat REST (send/patch) + Pub/Sub pull/ack. Empty disables the channel.
    google_chat_service_account_file: str = ""
    # Google Cloud project id that owns the Pub/Sub topic + subscription.
    google_chat_project_id: str = ""
    # Pub/Sub pull subscription id that receives inbound Chat events.
    google_chat_subscription_id: str = ""
    # When set, inbound Chat messages from this sender resource name
    # (e.g. ``users/1234567890``) auto-link to the seeded dev-admin user —
    # the single-user dogfood path. Unset → unbound senders are ignored.
    google_chat_dev_admin_id: str = ""


# Module singleton, mirroring ``app.infrastructure.config.settings``. Tests
# monkeypatch attributes on this instance.
google_chat_settings = GoogleChatSettings()

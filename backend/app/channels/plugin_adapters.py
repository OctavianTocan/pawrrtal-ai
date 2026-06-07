"""Factories used by bundled channel plugin manifests."""

from __future__ import annotations

from app.channels.base import Channel
from app.channels.google_chat.channel import GoogleChatChannel
from app.channels.sse import SSEChannel
from app.channels.telegram.channel import TelegramChannel
from app.plugins.contributions import ChannelCapability


def make_sse_channel(capability: ChannelCapability) -> Channel:
    """Build an SSE-backed channel for a manifest-declared surface."""
    return SSEChannel(surface=capability.surface)


def make_telegram_channel(_capability: ChannelCapability) -> Channel:
    """Build the Telegram channel adapter."""
    return TelegramChannel()


def make_google_chat_channel(_capability: ChannelCapability) -> Channel:
    """Build the Google Chat channel adapter."""
    return GoogleChatChannel()

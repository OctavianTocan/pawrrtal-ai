"""Compatibility re-exports for ORM models.

The canonical model modules live under :mod:`app.infrastructure.models`.
This shim keeps existing ``from app.models import ...`` imports working
while the rest of the backend is moved into domain packages.
"""

from __future__ import annotations

from app.infrastructure.models.channel import ChannelBinding, ChannelLinkCode
from app.infrastructure.models.conversation import ChatMessage, Conversation, SenderType
from app.infrastructure.models.dreaming import DreamingJob
from app.infrastructure.models.governance import (
    AuditEvent,
    CostLedger,
    ScheduledJob,
    WebhookEventRecord,
)
from app.infrastructure.models.lcm import (
    LCMContextItem,
    LCMEmbedding,
    LCMSummary,
    LCMSummarySource,
)
from app.infrastructure.models.mcp import McpServer
from app.infrastructure.models.memory import Memory
from app.infrastructure.models.notion import NotionOperationLog
from app.infrastructure.models.project import Project
from app.infrastructure.models.user_profile import (
    UserAppearance,
    UserPersonalization,
    UserPreferences,
)
from app.infrastructure.models.workspace import Workspace

__all__ = [
    "AuditEvent",
    "ChannelBinding",
    "ChannelLinkCode",
    "ChatMessage",
    "Conversation",
    "CostLedger",
    "DreamingJob",
    "LCMContextItem",
    "LCMEmbedding",
    "LCMSummary",
    "LCMSummarySource",
    "McpServer",
    "Memory",
    "NotionOperationLog",
    "Project",
    "ScheduledJob",
    "SenderType",
    "UserAppearance",
    "UserPersonalization",
    "UserPreferences",
    "WebhookEventRecord",
    "Workspace",
]

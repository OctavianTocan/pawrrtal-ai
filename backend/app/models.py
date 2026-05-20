"""SQLAlchemy ORM models for the application database.

Note: The ``User`` model lives in ``db.py`` because fastapi-users needs it
at import time. All other domain models are defined here.
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from .db_base import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    ``datetime.utcnow()`` is deprecated in Python 3.13 (returns a naive
    datetime that lies about its timezone). Centralised so every model
    default uses the same callable rather than re-importing UTC at the
    column site.
    """
    return datetime.now(UTC)


class SenderType(Enum):
    """Identifies who sent a message in a conversation."""

    AI = "ai"
    USER = "user"


class Conversation(Base):
    """Conversation metadata stored in the application database.

    Renderable message content lives in ``chat_messages``. Provider-native
    transcript stores are only used as implementation details.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_unread: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # "todo"|"in_progress"|"done"|null
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # JSON array of label IDs (e.g. ["bug", "feature"]). Validated against
    # the frontend pre-defined CHAT_LABELS list — the backend stores raw
    # IDs without enforcement so adding a new label client-side does not
    # require a migration. Defaults to an empty list rather than NULL so
    # `Conversation.labels.append(...)` always works without a None guard.
    labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Optional FK to the project this conversation belongs to. NULL means
    # the conversation lives in the unattached "Chats" list at the bottom
    # of the sidebar; setting it surfaces the row under the project's
    # nested children. ON DELETE SET NULL so removing a project keeps the
    # conversations around and just unattaches them.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # Channel that created this conversation (e.g. "telegram", "web").
    origin_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Telegram Bot API 9.3+ topic thread ID.  NULL for non-topic DMs.
    telegram_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Lifecycle marker for the auto-title feature:
    # NULL = not yet titled, "auto" = generated, "user" = user-edited.
    title_set_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Per-conversation verbose level for streaming UX (PR 07):
    # 0 = quiet (only deltas + errors), 1 = normal (+ tool_use names),
    # 2 = detailed (+ thinking + tool inputs). NULL inherits
    # settings.telegram_verbose_default (or 1 if unset).
    verbose_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-conversation reasoning depth. One of the ReasoningEffort literal
    # values ("low" | "medium" | "high" | "extra-high") or NULL to let the
    # provider pick its default. Mirrors verbose_level's plumbing: a chat
    # request may still override per-turn, but absent that the persisted
    # value is what the turn runner forwards to the provider.
    reasoning_effort: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Project(Base):
    """Top-level project users can drop conversations into.

    Pure organizational container — has no settings of its own today.
    Conversations point at it via ``Conversation.project_id``; deleting
    the project sets every linked conversation's ``project_id`` back to
    NULL rather than cascading.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UserPreferences(Base):
    """User preferences stored in the application database."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    font_size: Mapped[int] = mapped_column()


class UserPersonalization(Base):
    """Personalization profile filled in by the home-page wizard.

    1:1 with `user`. Every field is nullable so a partial profile (e.g.
    user skipped the ChatGPT-context step) round-trips cleanly through
    GET / PUT without coercing missing fields into empty strings.
    """

    __tablename__ = "user_personalization"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    goals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    connected_channels: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    chatgpt_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UserAppearance(Base):
    """Per-user theme overrides for the Settings → Appearance panel.

    1:1 with `user`. All fields are JSON blobs so the schema can grow
    (new color slots, new font slots, new behavioral toggles) without a
    migration per addition. Missing keys at the application layer fall
    back to the Mistral-inspired defaults baked into
    ``frontend/app/globals.css`` and mirrored in
    ``frontend/features/appearance/defaults.ts``. A fully empty row
    means "use the system defaults everywhere."

    Light and dark mode are tracked separately because dark mode is
    Codex/GitHub-adjacent in the Pawrrtal design system, not just
    inverted from light.
    """

    __tablename__ = "user_appearance"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    # Per-mode color overrides: { background, foreground, accent, info,
    # success, destructive }. Each value is a CSS color string (hex,
    # `oklch(...)`, etc.) that replaces the corresponding `--<role>` CSS
    # variable on `<html>` for that theme.
    light: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dark: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Font family overrides: { display, sans, mono }. Each is a raw CSS
    # font-family value (e.g. "Newsreader, Georgia, serif").
    fonts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Mode + global tweaks. See the Pydantic `AppearanceOptions` schema
    # for the canonical shape.
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ChannelLinkCode(Base):
    """A short-lived one-time-use code for linking a Pawrrtal user to a third-party channel."""

    __tablename__ = "channel_link_codes"

    # HMAC-SHA-256 hex hash of the user-facing code. PK so lookups are
    # by hash; the plaintext is never persisted.
    code_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Indexed because the cleanup job scans on (expires_at, used_at IS NULL)
    # to GC unredeemed codes; matches migration 007's ix_channel_link_codes_expires_at.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # NULL while the code is unredeemed; populated once the bot consumes it.
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelBinding(Base):
    """A binding between a Pawrrtal user and a third-party channel."""

    __tablename__ = "channel_bindings"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_user_id",
            name="uq_channel_bindings_provider_external_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The Pawrrtal user ID.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # Stable identity from the provider (Telegram user_id as text so the
    # column type is the same across providers).
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Default chat to push to. For Telegram direct chats this matches
    # external_user_id; for groups it's the chat where the bind happened.
    external_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Display handle captured at bind time. Surfaced in the Settings UI
    # connected-state ("@<display_handle>"); never trusted for auth.
    display_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Whether the Telegram chat has Topics (forum threads) enabled.
    has_topics_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class ChatMessage(Base):
    """A single chat message within a conversation, including reasoning state.

    This is the source of truth for what the chat UI renders on a refresh:
    role, plain-text content, thinking/reasoning text, tool invocations and
    their results, the arrival-ordered timeline, and the reasoning duration.
    Provider-agnostic turns write here; provider-native transcript stores
    are not used for rendering history.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id", ondelete="CASCADE"))
    # Stable insertion order within a conversation. Only ever increases —
    # regenerate replaces the row in place rather than allocating a new ordinal.
    ordinal: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, default="")
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON arrays — None when absent so the column shrinks to NULL on reads.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    timeline: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    thinking_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "streaming" | "complete" | "failed" — only meaningful on assistant rows.
    assistant_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Workspace-relative path to a file the agent delivered via send_message.
    attachment: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    # MIME type detected from the attachment path (e.g. "image/png").
    attachment_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Workspace(Base):
    """An agent workspace.

    A named directory on the host filesystem containing the standard
    OpenClaw-style file structure (AGENTS.md, SOUL.md, USER.md, IDENTITY.md,
    memory/, skills/, artifacts/).

    One user can own many workspaces.  The first workspace created for a user
    is flagged ``is_default=True`` and seeded automatically at the end of the
    onboarding flow using the user's ``UserPersonalization`` data.

    The ``path`` column is the absolute path on the host.  Agents that need
    filesystem access resolve the path from here rather than constructing it
    ad-hoc from the user ID.
    """

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Human-readable label shown in the UI (e.g. "Main", "Work", "Personal").
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Main")
    # Filesystem-safe slug used only as a readable hint alongside the UUID path.
    slug: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    # Absolute path to the workspace root directory on the host.
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    # Exactly one workspace per user should be the default at any given time.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LCMSummary(Base):
    """A single LCM summary node — either a leaf or a condensed parent."""

    __tablename__ = "lcm_summaries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 0 = leaf (summarises raw messages); 1+ = condensed (summarises other
    # summaries at depth-1).  Used by the condensation pass to decide which
    # nodes are eligible for the next level up.
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The actual summary prose the model produced.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Approximate token count of ``content`` — cached so the assembly + budget
    # math doesn't have to re-tokenise on every turn.
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Which model produced this summary (e.g. ``gemini-2.5-flash-preview-05-20``).
    # Stored so future re-compaction can pick a stronger model if needed.
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # "normal" | "aggressive" | "fallback" — mirrors the three-level escalation
    # used by the upstream plugin: normal prompt first, aggressive if the
    # output is too large, deterministic truncation if both LLM passes fail.
    summary_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LCMSummarySource(Base):
    """Edge from an :class:`LCMSummary` to one of its source items.

    A source is either a :class:`ChatMessage` (when the parent is a leaf
    summary) or another :class:`LCMSummary` (when the parent is a condensed
    summary).  ``source_kind`` discriminates between the two so a single
    join + filter recovers either flavour.
    """

    __tablename__ = "lcm_summary_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    summary_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("lcm_summaries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "message" | "summary" — string discriminator so the FK can target either.
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Position in the original ordering so re-assembly is deterministic.
    source_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class LCMContextItem(Base):
    """One entry in the assembled context list for a conversation.

    Walking this table in ``ordinal`` order produces the sequence of items
    fed to the provider every turn.  Each row points at either a raw
    :class:`ChatMessage` or a compacted :class:`LCMSummary`; the chat
    router resolves the actual content at assembly time.

    Compaction rewrites this list in place: a contiguous range of
    ``item_kind="message"`` rows is replaced by a single
    ``item_kind="summary"`` row, and the ordinals are renumbered so the
    list stays dense.
    """

    __tablename__ = "lcm_context_items"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "ordinal",
            name="uq_lcm_context_items_conv_ordinal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Position in the assembled list.  Gaps are harmless; ingest_message
    # uses max(ordinal)+1 so no dense renumbering after compaction.
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # "message" | "summary" — the discriminator the assembly step uses to
    # decide which lookup to perform.
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # FK target into either chat_messages or lcm_summaries depending on
    # ``item_kind``.  Cascades happen via the parent conversation_id FK.
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LCMEmbedding(Base):
    """Vector index entry for a single LCM-searchable item.

    Issue #254 (hybrid retrieval) needs a place to store one embedding
    per ``ChatMessage`` or ``LCMSummary`` so semantic search can run
    alongside the lexical scorer.  We keep the vectors as JSON arrays
    rather than introducing a pgvector dependency; that decision is
    documented in the issue and revisitable if production workloads
    demand it.  The ``content_hash`` column lets ingest skip
    re-embedding unchanged content; the ``UniqueConstraint`` ensures
    we only ever have one embedding per ``(conversation_id, item_kind,
    item_id, embedding_model)`` tuple.
    """

    __tablename__ = "lcm_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "item_kind",
            "item_id",
            "embedding_model",
            name="uq_lcm_embeddings_conv_kind_item_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "message" | "summary" - mirrors LCMContextItem.item_kind so a
    # search hit can be joined back to either source table.
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Identifier of the embedding provider that produced this vector.
    # Stored so a future migration to a stronger model can re-embed
    # in place without dropping the table.
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    # The embedding itself - stored as a JSON array of floats.  Length
    # is fixed per ``embedding_model`` but the database does not
    # enforce that; the ingest pipeline checks it.
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    # Content hash used to skip re-embedding when the underlying text
    # has not changed.  SHA-256 hex digest of the embedded text.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ---------------------------------------------------------------------------
# Governance + ops platform (PRs 01-12)
#
# Implementations live in :mod:`app.governance_models` to keep this file
# under the project's 500-line budget. Re-exported here so existing
# imports (`from app.models import AuditEvent`) keep working.
# ---------------------------------------------------------------------------

from .governance_models import (  # noqa: E402
    AuditEvent,
    CostLedger,
    ScheduledJob,
    WebhookEventRecord,
)
from .mcp_models import McpServer  # noqa: E402  (re-export — see mcp_models.py)


class NotionOperationLog(Base):
    """One row per tool call made by the Notion plugin.

    The Notion plugin shells out to the official ``ntn`` CLI; recording
    each invocation here lets the agent (via ``notion_logs_read``) and
    operators answer "what did this workspace do in Notion lately?"
    without scraping uvicorn logs.  Mirrors the SQLite schema used by
    openclaw-notion's ``audit.ts`` so prompts written against that
    contract Just Work here.

    Rows are workspace-scoped: the FK cascades on workspace delete so
    a workspace removal sweeps its history with it.
    """

    __tablename__ = "notion_operation_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Tool that produced this row.  E.g. "notion_search", "notion_create".
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Coarse operation bucket — "search", "read", "write", "delete", etc.
    # Useful when a single tool has multiple call shapes.
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    # Page / database / block IDs the call targeted, when known.  NULL when
    # the call was workspace-wide (search) or not page-scoped.
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    database_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # "ok" | "error" — outcome string.  Mirrored from openclaw-notion's
    # contract so log-reader prompts portable between hosts.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Wall-clock duration of the underlying ntn subprocess call.
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ntn stderr or thrown exception message; NULL on success.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw request / response JSON for debugging.  Stored even on success
    # because Notion's API surfaces are wide enough that grepping
    # human-readable history is genuinely useful.
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, index=True
    )


class Memory(Base):
    """A typed proactive memory written by the post-turn classifier or dreaming pass.

    Per the ADR at
    ``frontend/content/docs/handbook/decisions/2026-05-20-proactive-memory-updates.mdx``,
    the chat router runs a post-turn classifier that captures user
    preferences, project decisions, and explicit feedback. Each
    captured signal becomes a row here, typed by ``kind``.

    The dreaming pass (#341) reuses the same table — ``source`` is
    the provenance discriminator (``classifier`` / ``dreaming`` /
    ``user``) and ``provenance_job_id`` ties dreaming-written rows
    back to the job that wrote them.
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # One of ``feedback`` / ``project`` / ``user``. Pinned to that
    # set by ``ck_memories_kind_valid`` in migration 021.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # ``classifier`` (per-turn) | ``dreaming`` (between-sessions) |
    # ``user`` (manual). Pinned by ``ck_memories_source_valid``.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="classifier")
    # Set when ``source == "dreaming"`` — ties the row back to the
    # ``DreamingJob`` that wrote it (table introduced by #341).
    provenance_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Opaque bytes; the existing ``lcm/embeddings.py`` pipeline does
    # the per-provider serialisation. Promoted to ``pgvector`` later.
    embedding: Mapped[bytes | None] = mapped_column(nullable=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_referenced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = [
    "AuditEvent",
    "ChannelBinding",
    "ChannelLinkCode",
    "ChatMessage",
    "Conversation",
    "CostLedger",
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

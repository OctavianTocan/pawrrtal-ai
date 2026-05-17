"""Pydantic schemas for API request/response validation.

These are *not* database models — they define the shape of data flowing
through the API layer.
"""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi_users import schemas
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.core.config import settings
from app.core.providers.base import ReasoningEffort
from app.core.providers.catalog import default_model
from app.core.providers.model_id import InvalidModelId, parse_model_id

logger = logging.getLogger(__name__)


def _canonicalise_model_id(raw: str | None) -> str | None:
    """Rewrite any accepted input shape to canonical form.

    Canonical form is ``host:vendor/model``. ``None`` passes through.

    Raises:
        ValueError: If the string fails to parse (FastAPI maps this
            to HTTP 422).
    """
    if raw is None:
        return None
    try:
        return parse_model_id(raw).id
    except InvalidModelId as exc:
        # Re-raise as ValueError so Pydantic generates a clean 422.
        raise ValueError(str(exc)) from exc


def _canonicalise_model_id_for_read(raw: str | None) -> str | None:
    """Output validator for ``ConversationRead.model_id``.

    Defaults to strict (matches the input contract). When
    ``settings.strict_conversation_read_validation`` is ``False``,
    a non-canonical stored value falls back to the catalog default
    and is logged. Operator escape hatch, not a documented contract.
    """
    if raw is None:
        return None
    try:
        return parse_model_id(raw).id
    except InvalidModelId as exc:
        if settings.strict_conversation_read_validation:
            raise ValueError(str(exc)) from exc
        logger.warning(
            "CONVERSATION_READ_FALLBACK bad_model_id=%r error=%s",
            raw,
            exc,
        )
        return default_model().id


CanonicalModelId = Annotated[str | None, AfterValidator(_canonicalise_model_id)]
CanonicalModelIdForRead = Annotated[str | None, AfterValidator(_canonicalise_model_id_for_read)]

# --- User schemas (provided by fastapi-users) --------------------------------


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Response schema for user data (id, email, is_active, etc.)."""

    pass


class UserCreate(schemas.BaseUserCreate):
    """Request schema for user registration (email, password)."""

    pass


class UserUpdate(schemas.BaseUserUpdate):
    """Request schema for updating user profile."""

    pass


# --- Conversation schemas ----------------------------------------------------


ConversationTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class ConversationCreate(BaseModel):
    """Request schema for creating a conversation.

    The ``id`` is optional — when provided, the backend uses it as the
    primary key (allowing the frontend to pre-generate UUIDs). The optional
    title lets the frontend immediately show a first-message fallback before
    LLM title generation finishes.
    """

    id: uuid.UUID | None = None
    title: ConversationTitle | None = None


class ConversationRead(BaseModel):
    """Response schema returned for conversation endpoints."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False
    is_flagged: bool = False
    is_unread: bool = False
    status: str | None = None
    model_id: CanonicalModelIdForRead = None
    # Always serialized as a list (never null) so the frontend never has to
    # narrow with `?? []` before iterating.
    labels: list[str] = []
    # ID of the project this conversation belongs to, or null when the
    # conversation lives in the unattached "Chats" list.
    project_id: uuid.UUID | None = None


class ConversationUpdate(BaseModel):
    """Request schema for updating mutable conversation fields."""

    title: ConversationTitle | None = None
    is_archived: bool | None = None
    is_flagged: bool | None = None
    is_unread: bool | None = None
    status: str | None = None
    model_id: CanonicalModelId = None  # optional — only set when changing model
    # Optional in the PATCH body — when provided, fully replaces the row's
    # label set. Sentinel `None` means "leave labels unchanged" (matches the
    # other partial-update fields above).
    labels: list[str] | None = None
    # Drag-and-drop assignment uses an explicit two-state sentinel so the
    # frontend can distinguish "leave alone" (omit the field entirely) from
    # "remove from current project" (send null). Pydantic gives us this for
    # free via `Field(default=...)` — omission keeps the SQLAlchemy column
    # untouched, while explicit None unsets the FK.
    project_id: uuid.UUID | None = Field(default=None)
    # Companion flag: explicit "treat project_id as set, even when null".
    # Without this, JSON `{"project_id": null}` is indistinguishable from
    # an omitted field after Pydantic coercion. The CRUD service reads this
    # flag and only touches `project_id` when it's true.
    project_id_set: bool = False


class ProjectRead(BaseModel):
    """Response schema returned for project endpoints."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    """Request schema for creating a new project."""

    name: str


class ProjectUpdate(BaseModel):
    """Request schema for renaming an existing project."""

    name: str | None = None


# --- Personalization schemas --------------------------------------------------


class PersonalizationProfile(BaseModel):
    """Home-page personalization wizard profile.

    Mirrors the frontend `PersonalizationProfile` interface in
    `frontend/features/personalization/storage.ts`. Every field is
    optional so a partially-filled wizard round-trips cleanly. Used
    as both the GET response and the PUT request body — the endpoint
    treats the request as a full replacement of the persisted profile.
    """

    name: str | None = None
    company_website: str | None = None
    linkedin: str | None = None
    role: str | None = None
    goals: list[str] | None = None
    connected_channels: list[str] | None = None
    chatgpt_context: str | None = None
    personality: str | None = None
    custom_instructions: str | None = None


# --- Appearance schemas -------------------------------------------------------


class ThemeColors(BaseModel):
    """Per-mode color overrides for the Pawrrtal design system.

    All fields optional — a missing key means "use the system default"
    (the Mistral-inspired tokens in ``frontend/app/globals.css``). Each
    value is a raw CSS color string and lands directly on the
    corresponding ``--<role>`` CSS custom property at runtime.
    """

    background: str | None = None
    foreground: str | None = None
    accent: str | None = None
    info: str | None = None
    success: str | None = None
    destructive: str | None = None


class AppearanceFonts(BaseModel):
    """Font family overrides applied to the type system."""

    display: str | None = None
    sans: str | None = None
    mono: str | None = None


class AppearanceOptions(BaseModel):
    """Mode + behavioral tweaks for the appearance system.

    ``theme_mode`` controls which palette is active (light/dark/system).
    ``contrast`` and ``ui_font_size`` are numeric so the frontend can
    drive sliders / number inputs without re-coercing. ``translucent_sidebar``
    and ``pointer_cursors`` are boolean toggles shown in the panel.
    """

    theme_mode: str | None = None
    translucent_sidebar: bool | None = None
    contrast: int | None = None
    pointer_cursors: bool | None = None
    ui_font_size: int | None = None


class AppearanceSettings(BaseModel):
    """Per-user theme overrides for the Settings → Appearance panel.

    Mirrors the frontend ``AppearanceSettings`` type in
    ``frontend/features/appearance/types.ts``. Used as both the GET
    response and the PUT request body — the endpoint treats the
    request as a full replacement of the persisted settings, so partial
    customizations (e.g. only changing the accent color) round-trip
    cleanly. Missing keys fall back to the Mistral-inspired defaults
    baked into the frontend.
    """

    light: ThemeColors = ThemeColors()
    dark: ThemeColors = ThemeColors()
    fonts: AppearanceFonts = AppearanceFonts()
    options: AppearanceOptions = AppearanceOptions()


# --- Chat schemas -------------------------------------------------------------


class ChatImageInput(BaseModel):
    """One multimodal image attached to a chat request (PR 09).

    Wire shape matches what both the Claude SDK and Gemini SDK expect
    after the provider-specific bridge translates: a base64-encoded
    blob plus an explicit MIME type.  The frontend composer handles
    the data-URL → base64 split before POSTing.
    """

    data: str  # base64-encoded image bytes (no data: URL prefix)
    media_type: Literal["image/png", "image/jpeg", "image/gif", "image/webp"] = "image/png"


# Cap on images per chat request — generous enough for pasting a
# short slideshow but bounded so a malicious client can't blow up
# the prompt budget.
MAX_IMAGES_PER_REQUEST = 8


class ChatRequest(BaseModel):
    """Request schema for the ``POST /api/v1/chat`` streaming endpoint.

    Attributes:
        question: The user's message to send to the selected model.
        conversation_id: UUID linking this message to a conversation.
        model_id: The ID of the model to use for the agent.
        reasoning_effort: Optional reasoning-depth knob from the chat composer.
        images: Optional list of multimodal image inputs (PR 09).
            Each item is a base64-encoded blob + MIME type the
            provider plumbs into a multimodal content block.
    """

    question: str
    conversation_id: uuid.UUID
    model_id: CanonicalModelId = None
    reasoning_effort: ReasoningEffort | None = None
    images: list[ChatImageInput] | None = None


class ChatResponse(BaseModel):
    """Response schema for non-streaming chat responses.

    Attributes:
        response: The agent's reply text.
    """

    response: str


# --- Chat history schemas -----------------------------------------------------


class ChatMessageRead(BaseModel):
    """Single rehydrated chat message returned by ``GET /conversations/:id/messages``.

    Mirrors the chat message shape consumed by the frontend so the chat UI
    can render past turns with the same chain-of-thought, tool steps, source
    chips, and reasoning duration as the live stream produced.
    """

    role: Literal["user", "assistant"]
    content: str
    thinking: str | None = None
    # The frontend expects the snake_case field names below; matching them here
    # avoids a serializer alias dance on the read path.
    tool_calls: list[dict[str, Any]] | None = None
    timeline: list[dict[str, Any]] | None = None
    thinking_duration_seconds: int | None = None
    assistant_status: Literal["streaming", "complete", "failed"] | None = None


# --- Channel schemas ---------------------------------------------------------


class ChannelBindingRead(BaseModel):
    """Public shape returned by ``GET /api/v1/channels``."""

    provider: str
    external_user_id: str
    # external_chat_id + display_handle remain on the read shape because
    # the Settings UI renders the handle (``@{display_handle}``) on the
    # connected-state dialog and the binding hook reads the chat id.
    external_chat_id: str | None = None
    display_handle: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TelegramLinkCodeRead(BaseModel):
    """Response shape from ``POST /api/v1/channels/telegram/link``.

    Always constructed from scalar kwargs by the route — never
    ``.model_validate(orm_row)``. The closest ORM row (``ChannelLinkCode``)
    only stores ``code_hash``, never the plaintext ``code`` returned here,
    so attribute-mode validation would be a bug, not a convenience.
    """

    code: str
    expires_at: datetime
    bot_username: str | None = None
    deep_link: str | None = None


# --- Workspace schemas --------------------------------------------------------


class WorkspaceRead(BaseModel):
    """Workspace summary returned by list / detail endpoints."""

    id: uuid.UUID
    name: str
    slug: str
    path: str
    is_default: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OnboardingStatus(BaseModel):
    """Onboarding readiness response for authenticated users."""

    has_workspace_ready: bool
    workspace: WorkspaceRead | None = None


class WorkspaceFileNode(BaseModel):
    """A single node in a workspace file-tree response."""

    name: str
    path: str  # workspace-relative path, e.g. "memory/2026-05-06.md"
    is_dir: bool
    size: int | None = None  # None for directories


class WorkspaceTreeResponse(BaseModel):
    """Recursive file tree rooted at the workspace directory."""

    workspace_id: uuid.UUID
    nodes: list[WorkspaceFileNode]


class WorkspaceFileContent(BaseModel):
    """Contents of a single workspace file."""

    path: str
    content: str


class WorkspaceFileWrite(BaseModel):
    """Payload for writing a workspace file."""

    content: str


class SkillRead(BaseModel):
    """A single skill entry returned by GET /{workspace_id}/skills."""

    name: str
    trigger: str
    summary: str
    has_skill_md: bool


# --- Governance + ops platform schemas ---------------------------------------
#
# Implementations live in :mod:`app.governance_schemas` to keep this
# file under the project's 500-line budget. Re-exported here so
# existing imports (``from app.schemas import AuditEventRead``) keep
# working.

from .governance_schemas import (  # noqa: E402,F401
    DEFAULT_GOVERNANCE_PAGE_SIZE,
    MAX_GOVERNANCE_PAGE_SIZE,
    AuditEventRead,
    CostLedgerRead,
    CostSummaryRead,
    ScheduledJobCreate,
    ScheduledJobRead,
    ScheduledJobUpdate,
    WebhookEventRead,
)

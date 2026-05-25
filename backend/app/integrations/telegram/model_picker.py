"""Catalog-backed Telegram model picker helpers.

Three-level walk: host → vendor → models (single-vendor hosts collapse to two levels).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import CATALOG_ETAG, MODEL_CATALOG, ModelEntry
from app.core.providers.labels import host_label_from_slug, vendor_label_from_slug
from app.crud.channel import get_or_create_telegram_conversation_full, get_user_id_for_external
from app.crud.user_preferences import get_user_default_model_id
from app.integrations.telegram.model_auth import is_host_authenticated
from app.integrations.telegram.model_defaults import resolve_effective_model_id

ModelCallbackAction = Literal["providers", "vendors", "list", "select", "set_default"]

PROVIDER = "telegram"
MODEL_CALLBACK_PREFIX = "mdl:"
_CATALOG_TOKEN = CATALOG_ETAG[:8]
_MODEL_PAGE_SIZE = 8
_HOST_BUTTONS_PER_ROW = 2
_VENDOR_BUTTONS_PER_ROW = 2
_CALLBACK_MIN_PARTS = 2  # mdl:<tag>...
_CALLBACK_VENDOR_PARTS = 3  # mdl:v:<host>
_CALLBACK_LIST_PARTS = 5  # mdl:l:<host>:<vendor>:<page>
_CALLBACK_SELECT_PARTS = 4  # mdl:s:<token>:<index>
_CALLBACK_DEFAULT_PARTS = 4  # mdl:d:<token>:<index>

_PICKER_NOT_BOUND_MESSAGE = "Connect your account first before changing models."
_PICKER_STALE_MESSAGE = "That model picker is out of date. Send /model again."
_DEFAULT_BUTTON_TEXT = "⭐ Set as my default"
_DEFAULT_ALREADY_SET_TEXT = "⭐ Already your default"
# Inert callback used by the post-default badge so a second tap is a no-op.
NOOP_CALLBACK = "mdl:noop"


class TelegramSenderLike(Protocol):
    """Subset of ``TelegramSender`` used by picker state resolution."""

    @property
    def user_id(self) -> int:
        """Telegram numeric user id."""
        ...

    @property
    def thread_id(self) -> int | None:
        """Telegram topic thread id, or ``None`` outside a topic."""
        ...


@dataclass(frozen=True)
class ModelButton:
    """One Telegram inline keyboard button."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class ModelPickerState:
    """Current catalog state for one Telegram conversation."""

    current_model_id: str
    # Persisted per-user default (or ``None``) — drives whether the
    # picker offers "set as default" affordances after a selection.
    user_default_model_id: str | None = None


@dataclass(frozen=True)
class ModelCallback:
    """Parsed Telegram callback payload for the model picker."""

    action: ModelCallbackAction
    host: str | None = None
    provider: str | None = None  # vendor slug; name kept for runtime compatibility
    page: int = 1
    index: int | None = None
    catalog_token: str | None = None


async def get_model_picker_state(
    *,
    sender: TelegramSenderLike,
    session: AsyncSession,
) -> ModelPickerState | None:
    """Resolve the current model + user default for a Telegram sender.

    Returns ``None`` when the Telegram sender is not bound to a user.
    """
    pawrrtal_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if pawrrtal_user_id is None:
        return None

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    current_model_id = await resolve_effective_model_id(
        session=session,
        user_id=pawrrtal_user_id,
        conversation_model_id=conversation.model_id,
    )
    user_default = await get_user_default_model_id(
        session=session,
        user_id=pawrrtal_user_id,
    )
    return ModelPickerState(
        current_model_id=current_model_id,
        user_default_model_id=user_default,
    )


def build_host_keyboard() -> list[list[ModelButton]]:
    """Build a two-column host picker from the catalog."""
    rows: list[list[ModelButton]] = []
    current_row: list[ModelButton] = []
    for host, vendors in _host_to_vendors().items():
        total = sum(len(entries) for entries in vendors.values())
        current_row.append(
            ModelButton(
                text=f"{host_label_from_slug(host)} ({total})",
                callback_data=_host_button_callback(host=host, vendors=vendors),
            )
        )
        if len(current_row) == _HOST_BUTTONS_PER_ROW:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    return rows


def build_vendor_keyboard(*, host: str) -> list[list[ModelButton]]:
    """Build the vendor keyboard for a host with multiple vendors."""
    vendors = _host_to_vendors().get(host, {})
    rows: list[list[ModelButton]] = []
    current_row: list[ModelButton] = []
    for vendor, entries in vendors.items():
        current_row.append(
            ModelButton(
                text=f"{vendor_label_from_slug(vendor)} ({len(entries)})",
                callback_data=_list_callback(host=host, vendor=vendor, page=1),
            )
        )
        if len(current_row) == _VENDOR_BUTTONS_PER_ROW:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([ModelButton(text="Back to providers", callback_data=_providers_callback())])
    return rows


def build_models_keyboard(
    *,
    host: str,
    vendor: str,
    page: int,
    current_model_id: str,
) -> list[list[ModelButton]]:
    """Build a paginated model keyboard for one host+vendor pair.

    The trailing "Back to ..." row collapses to "Back to providers" when
    the host has a single vendor, since the vendor screen was skipped on
    the way in.
    """
    vendors = _host_to_vendors().get(host, {})
    entries = vendors.get(vendor, [])
    page_count = _page_count(entries)
    page = _clamped_page(page, page_count)
    page_entries = _page_entries(entries, page)

    rows: list[list[ModelButton]] = [
        [
            ModelButton(
                text=_model_label(entry, current_model_id),
                callback_data=_select_callback(_catalog_index(entry)),
            )
        ]
        for entry in page_entries
    ]
    rows.extend(_pagination_rows(host=host, vendor=vendor, page=page, page_count=page_count))
    if len(vendors) > 1:
        rows.append([ModelButton(text="Back to vendors", callback_data=_vendor_callback(host))])
    else:
        rows.append([ModelButton(text="Back to providers", callback_data=_providers_callback())])
    return rows


def has_host(host: str) -> bool:
    """Return whether the catalog has at least one model for ``host``."""
    return host in _host_to_vendors()


def has_vendor_in_host(*, host: str, vendor: str) -> bool:
    """Return whether ``vendor`` has at least one model under ``host``."""
    return vendor in _host_to_vendors().get(host, {})


def format_host_picker_text(
    current_model_id: str,
    user_default_model_id: str | None = None,
) -> str:
    """Render the host picker message in Telegram HTML.

    Surfaces a second "Default: …" line when the user has pinned a
    default that differs from the conversation's current model.
    """
    current = _display_name_for_model(current_model_id)
    lines = [
        "Choose a provider for this Telegram conversation.",
        "",
        f"Current: <b>{escape(current)}</b>",
    ]
    if user_default_model_id and user_default_model_id != current_model_id:
        default_name = _display_name_for_model(user_default_model_id)
        lines.append(f"Default: <b>{escape(default_name)}</b> ⭐")
    return "\n".join(lines)


def format_vendor_picker_text(*, host: str) -> str:
    """Render the vendor screen header in Telegram HTML."""
    return f"Select a vendor for <b>{escape(host_label_from_slug(host))}</b>."


def format_models_picker_text(*, host: str, vendor: str, page: int) -> str:
    """Render the model page header in Telegram HTML."""
    entries = _host_to_vendors().get(host, {}).get(vendor, [])
    page_count = _page_count(entries)
    page = _clamped_page(page, page_count)
    return (
        f"Select a {escape(vendor_label_from_slug(vendor))} model "
        f"on <b>{escape(host_label_from_slug(host))}</b>.\nPage {page}/{page_count}"
    )


def parse_model_callback_data(data: str | None) -> ModelCallback | None:
    """Parse Telegram callback data generated by this module."""
    if data == _providers_callback() or data == "mdl:b":
        return ModelCallback(action="providers")
    if data is None or not data.startswith(MODEL_CALLBACK_PREFIX):
        return None

    parts = data.split(":")
    return _parse_prefixed_callback(parts)


def _parse_prefixed_callback(parts: list[str]) -> ModelCallback | None:
    # Minimum length is `mdl:<tag>` (two parts); below that there's no
    # tag byte to read and we'd index past the end.
    if len(parts) < _CALLBACK_MIN_PARTS:
        return None
    tag = parts[1]
    if len(parts) == _CALLBACK_VENDOR_PARTS and tag == "v":
        return ModelCallback(action="vendors", host=parts[2])
    if len(parts) == _CALLBACK_LIST_PARTS and tag == "l":
        return _parse_list_callback(parts)
    if len(parts) == _CALLBACK_SELECT_PARTS and tag == "s":
        return _parse_indexed_callback(parts, "select")
    if len(parts) == _CALLBACK_DEFAULT_PARTS and tag == "d":
        return _parse_indexed_callback(parts, "set_default")
    return None


def resolve_model_selection(callback: ModelCallback) -> ModelEntry | None:
    """Resolve a ``select`` / ``set_default`` callback to a catalog entry.

    Returns ``None`` for stale catalog tokens or out-of-range indexes.
    """
    if callback.action not in ("select", "set_default"):
        return None
    if callback.catalog_token != _CATALOG_TOKEN:
        return None
    if callback.index is None or callback.index < 0 or callback.index >= len(MODEL_CATALOG):
        return None
    return MODEL_CATALOG[callback.index]


def build_set_default_keyboard(*, model_id: str) -> list[list[ModelButton]] | None:
    """Build the "⭐ Set as my default" row, or ``None`` for stale catalog."""
    entry = _entry_by_id(model_id)
    if entry is None:
        return None
    return [
        [
            ModelButton(
                text=_DEFAULT_BUTTON_TEXT,
                callback_data=_set_default_callback(_catalog_index(entry)),
            )
        ]
    ]


def build_default_already_set_keyboard() -> list[list[ModelButton]]:
    """Build the inert "⭐ Already your default" confirmation row."""
    return [[ModelButton(text=_DEFAULT_ALREADY_SET_TEXT, callback_data=NOOP_CALLBACK)]]


def picker_not_bound_message() -> str:
    """Return the not-bound message for picker entry points."""
    return _PICKER_NOT_BOUND_MESSAGE


def picker_stale_message() -> str:
    """Return the stale-picker callback message."""
    return _PICKER_STALE_MESSAGE


def _host_to_vendors() -> dict[str, dict[str, list[ModelEntry]]]:
    """Group the catalog as ``{host_slug: {vendor_slug: [entries]}}``.

    Hosts whose gateway-global API key is absent are filtered out so
    the picker only shows providers the user can actually invoke
    (#370). Both layers preserve a stable, alphabetised order so the
    keyboards are deterministic.
    """
    grouped: dict[str, dict[str, list[ModelEntry]]] = {}
    for entry in MODEL_CATALOG:
        host_slug = entry.host.value
        if not is_host_authenticated(host_slug):
            continue
        host_bucket = grouped.setdefault(host_slug, {})
        host_bucket.setdefault(entry.vendor.value, []).append(entry)
    return {host: dict(sorted(vendors.items())) for host, vendors in sorted(grouped.items())}


def _host_button_callback(*, host: str, vendors: dict[str, list[ModelEntry]]) -> str:
    """Callback for a host button — collapses single-vendor hosts to the model list."""
    if len(vendors) == 1:
        only_vendor = next(iter(vendors))
        return _list_callback(host=host, vendor=only_vendor, page=1)
    return _vendor_callback(host)


def _model_label(entry: ModelEntry, current_model_id: str) -> str:
    prefix = "Selected: " if entry.id == current_model_id else ""
    return f"{prefix}{entry.display_name}"


def _display_name_for_model(model_id: str) -> str:
    entry = _entry_by_id(model_id)
    return entry.display_name if entry else model_id


def _catalog_index(entry: ModelEntry) -> int:
    return MODEL_CATALOG.index(entry)


def _providers_callback() -> str:
    return "mdl:p"


def _vendor_callback(host: str) -> str:
    return f"mdl:v:{host}"


def _list_callback(*, host: str, vendor: str, page: int) -> str:
    return f"mdl:l:{host}:{vendor}:{page}"


def _select_callback(index: int) -> str:
    return f"mdl:s:{_CATALOG_TOKEN}:{index}"


def _set_default_callback(index: int) -> str:
    return f"mdl:d:{_CATALOG_TOKEN}:{index}"


def _entry_by_id(model_id: str) -> ModelEntry | None:
    """Look up a catalog entry by its canonical ``host:vendor/model`` ID."""
    for entry in MODEL_CATALOG:
        if entry.id == model_id:
            return entry
    return None


def _parse_list_callback(parts: list[str]) -> ModelCallback | None:
    try:
        page = int(parts[4])
    except ValueError:
        return None
    if page < 1:
        return None
    return ModelCallback(
        action="list",
        host=parts[2],
        provider=parts[3],
        page=page,
    )


def _parse_indexed_callback(
    parts: list[str],
    action: ModelCallbackAction,
) -> ModelCallback | None:
    try:
        index = int(parts[3])
    except ValueError:
        return None
    return ModelCallback(action=action, index=index, catalog_token=parts[2])


def _page_count(entries: list[ModelEntry]) -> int:
    return max(1, math.ceil(len(entries) / _MODEL_PAGE_SIZE))


def _clamped_page(page: int, page_count: int) -> int:
    return min(max(page, 1), page_count)


def _page_entries(entries: list[ModelEntry], page: int) -> list[ModelEntry]:
    start = (page - 1) * _MODEL_PAGE_SIZE
    return entries[start : start + _MODEL_PAGE_SIZE]


def _pagination_rows(
    *,
    host: str,
    vendor: str,
    page: int,
    page_count: int,
) -> list[list[ModelButton]]:
    if page_count <= 1:
        return []
    row: list[ModelButton] = []
    if page > 1:
        row.append(
            ModelButton(
                text="< Prev",
                callback_data=_list_callback(host=host, vendor=vendor, page=page - 1),
            )
        )
    row.append(
        ModelButton(
            text=f"{page}/{page_count}",
            callback_data=_list_callback(host=host, vendor=vendor, page=page),
        )
    )
    if page < page_count:
        row.append(
            ModelButton(
                text="Next >",
                callback_data=_list_callback(host=host, vendor=vendor, page=page + 1),
            )
        )
    return [row]


__all__ = [
    "MODEL_CALLBACK_PREFIX",
    "NOOP_CALLBACK",
    "ModelButton",
    "ModelCallback",
    "ModelPickerState",
    "TelegramSenderLike",
    "build_default_already_set_keyboard",
    "build_host_keyboard",
    "build_models_keyboard",
    "build_set_default_keyboard",
    "build_vendor_keyboard",
    "format_host_picker_text",
    "format_models_picker_text",
    "format_vendor_picker_text",
    "get_model_picker_state",
    "has_host",
    "has_vendor_in_host",
    "parse_model_callback_data",
    "picker_not_bound_message",
    "picker_stale_message",
    "resolve_model_selection",
]

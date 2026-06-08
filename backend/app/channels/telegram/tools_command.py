"""Telegram `/tools` command for the live agent tool surface."""

from __future__ import annotations

import html
from collections import defaultdict
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tool_surface import build_agent_tools
from app.agents.types import AgentTool
from app.channels.crud import get_or_create_telegram_conversation_full
from app.channels.telegram.dev_admin import resolve_or_autolink_telegram_user
from app.channels.telegram.model_defaults import resolve_effective_model_id
from app.channels.telegram.sender import TelegramSender
from app.plugins.capability_catalog import CapabilityRecord
from app.plugins.errors import PluginError
from app.plugins.host import get_plugin_host
from app.workspace.crud import get_default_workspace

_NOT_BOUND_MESSAGE = "Connect your account first before listing tools."
_NO_WORKSPACE_MESSAGE = "Finish workspace onboarding before listing tools."
_MAX_TOOL_ROWS = 40
_MAX_CAPABILITY_ROWS = 40


async def handle_tools_command(*, sender: TelegramSender, session: AsyncSession) -> str:
    """Return the concrete tools and plugin capabilities for this Telegram turn."""
    pawrrtal_user_id = await resolve_or_autolink_telegram_user(session=session, sender=sender)
    if pawrrtal_user_id is None:
        return _NOT_BOUND_MESSAGE

    workspace = await get_default_workspace(pawrrtal_user_id, session)
    if workspace is None:
        return _NO_WORKSPACE_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        user_id=pawrrtal_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    model_id = resolve_effective_model_id(conversation_model_id=conversation.model_id)
    workspace_root = Path(workspace.path)
    tools = build_agent_tools(
        workspace_root=workspace_root,
        user_id=pawrrtal_user_id,
        workspace_id=workspace.id,
        send_fn=_noop_send,
        surface="telegram",
        conversation_id=conversation.id,
        model_id=model_id,
    )
    capabilities, plugin_error = _load_enabled_capabilities(workspace_root=workspace_root)
    return _render_tools_message(
        model_id=model_id,
        tools=tools,
        capabilities=capabilities,
        plugin_error=plugin_error,
    )


async def _noop_send(
    _text: str | None,
    _file_path: Path | None,
    _mime: str | None,
) -> None:
    """Let `/tools` include channel delivery tools without sending anything."""


def _load_enabled_capabilities(
    *,
    workspace_root: Path,
) -> tuple[tuple[CapabilityRecord, ...], str | None]:
    try:
        _previous, snapshot = get_plugin_host().reload(workspace_root=workspace_root)
    except PluginError as exc:
        return (), str(exc)
    return tuple(row for row in snapshot.capabilities if row.state == "enabled"), None


def _render_tools_message(
    *,
    model_id: str,
    tools: list[AgentTool],
    capabilities: tuple[CapabilityRecord, ...],
    plugin_error: str | None,
) -> str:
    lines = [
        "<b>Tools available</b>",
        f"Model: <code>{html.escape(model_id)}</code>",
        "",
        f"<b>Agent tools ({len(tools)})</b>",
        *_render_tool_rows(tools),
        "",
        f"<b>Enabled plugin capabilities ({len(capabilities)})</b>",
        *_render_capability_rows(capabilities),
    ]
    if plugin_error is not None:
        lines.extend(("", f"Plugin catalog error: <code>{html.escape(plugin_error)}</code>"))
    return "\n".join(lines)


def _render_tool_rows(tools: list[AgentTool]) -> list[str]:
    if not tools:
        return ["none"]
    names = sorted({tool.name for tool in tools})
    rows = [f"- <code>{html.escape(name)}</code>" for name in names[:_MAX_TOOL_ROWS]]
    return _with_more_row(rows, total=len(names), shown=len(rows))


def _render_capability_rows(capabilities: tuple[CapabilityRecord, ...]) -> list[str]:
    if not capabilities:
        return ["none"]

    by_slot: dict[str, list[CapabilityRecord]] = defaultdict(list)
    for capability in capabilities:
        slots = capability.slots or ("unslotted",)
        for slot in slots:
            by_slot[slot].append(capability)

    rows: list[str] = []
    for slot in sorted(by_slot):
        rows.append(f"- <b>{html.escape(slot)}</b>")
        for capability in sorted(by_slot[slot], key=lambda row: row.key):
            if len(rows) >= _MAX_CAPABILITY_ROWS:
                return _with_more_row(rows, total=_capability_row_count(by_slot), shown=len(rows))
            rows.append(
                f"  - <code>{html.escape(capability.key)}</code> ({html.escape(capability.type)})"
            )
    return rows


def _capability_row_count(by_slot: dict[str, list[CapabilityRecord]]) -> int:
    return len(by_slot) + sum(len(rows) for rows in by_slot.values())


def _with_more_row(rows: list[str], *, total: int, shown: int) -> list[str]:
    hidden = total - shown
    if hidden > 0:
        rows.append(f"- ...and {hidden} more")
    return rows

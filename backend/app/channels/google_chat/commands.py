"""Slash-command handling for the Google Chat channel.

Commands arrive either as configured slash commands (under
``chat.appCommandPayload``, which gives autocomplete in the Chat UI) or as
plain ``/cmd`` text typed before any Console config exists;
:func:`app.channels.google_chat.messages.parse_command` normalizes both to
``(command, args)``. Each handler returns the reply text the ingress posts
back into the space, and maps onto the same conversation CRUD the Telegram
commands use so behavior stays consistent across channels.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.crud import (
    update_conversation_model,
    update_conversation_reasoning_effort,
    update_conversation_verbose_level,
)
from app.infrastructure.keys import load_workspace_env, save_workspace_env
from app.models import Conversation
from app.providers.base import ReasoningEffort
from app.providers.selection import effective_model_id, model_display
from app.workspace.crud import get_default_workspace

from .conversation import start_new_google_chat_conversation
from .delivery import DEFAULT_VERBOSE_LEVEL
from .lcm_commands import lcm_status_text, run_compaction

# Reasoning levels the model layer understands, plus "none" to clear the
# override. Sourced from the real ``ReasoningEffort`` literal so this never
# drifts from what the providers accept.
_REASONING_LEVELS: tuple[str, ...] = get_args(ReasoningEffort)
_REASONING_CLEAR = "none"

_VERBOSE_LABELS = {0: "quiet", 1: "tools", 2: "thinking"}
_VERBOSE_CHOICES = {"0", "1", "2"}

# (command, description) — the user-facing menu. ``/help`` prints it, and an
# operator registers these names as Chat slash commands (Chat API →
# Configuration → Commands) to get autocomplete; the dispatch keys off the
# command text either way.
COMMAND_MENU: tuple[tuple[str, str], ...] = (
    ("help", "List the available commands"),
    ("new", "Start a fresh conversation"),
    ("model", "Show or set the model for this conversation"),
    ("thinking", "Show or set reasoning effort (none|low|medium|high)"),
    ("verbose", "Set detail level: 0 quiet, 1 tools, 2 thinking"),
    ("config", "Toggle workspace features (active recall, search)"),
    ("status", "Show model, verbosity, and reasoning for this conversation"),
    ("whoami", "Show your Chat identity and Pawrrtal binding"),
    ("lcm", "Show long-context-memory status"),
    ("compact", "Force a memory-compaction pass now"),
    ("stop", "How to interrupt a run on this channel"),
)

# /config workspace toggles: name → (env key, label, default-on).
_CONFIG_TOGGLES: dict[str, tuple[str, str, bool]] = {
    "active_recall": ("ACTIVE_RECALL_ENABLED", "Active Recall", True),
    "search_workspace": ("ACTIVE_RECALL_SEARCH_WORKSPACE", "Search Workspace", False),
}
# "/config <toggle> <on|off>" → exactly two space-separated args.
_CONFIG_TOGGLE_ARGS = 2


@dataclass
class CommandContext:
    """Everything a command handler needs, resolved by the ingress."""

    user_id: uuid.UUID
    conversation: Conversation
    args: str
    sender_resource: str
    sender_email: str | None
    session: AsyncSession


async def dispatch_command(*, command: str, ctx: CommandContext) -> str:
    """Run *command* and return the reply text (never raises for the user)."""
    handler = _HANDLERS.get(command)
    if handler is None:
        return f"Unknown command /{command}. Try /help."
    return await handler(ctx)


def _verbose_of(conversation: Conversation) -> int:
    level = conversation.verbose_level
    return level if level is not None else DEFAULT_VERBOSE_LEVEL


async def _cmd_help(ctx: CommandContext) -> str:
    lines = ["*Pawrrtal commands*"]
    lines.extend(f"• /{name} — {desc}" for name, desc in COMMAND_MENU)
    return "\n".join(lines)


async def _cmd_new(ctx: CommandContext) -> str:
    await start_new_google_chat_conversation(user_id=ctx.user_id, session=ctx.session)
    return "🆕 Started a fresh conversation. Earlier history is set aside."


async def _cmd_whoami(ctx: CommandContext) -> str:
    lines = [f"*Chat identity*: {ctx.sender_resource}"]
    if ctx.sender_email:
        lines.append(f"*Email*: {ctx.sender_email}")
    lines.append(f"*Pawrrtal user*: {ctx.user_id}")
    return "\n".join(lines)


async def _cmd_status(ctx: CommandContext) -> str:
    conv = ctx.conversation
    model = model_display(conv.model_id, default_suffix=True)
    verbose = _verbose_of(conv)
    reasoning = conv.reasoning_effort or "provider default"
    return (
        "*Status*\n"
        f"• Model: {model}\n"
        f"• Verbosity: {verbose} ({_VERBOSE_LABELS.get(verbose, '?')})\n"
        f"• Reasoning: {reasoning}"
    )


async def _cmd_model(ctx: CommandContext) -> str:
    if not ctx.args:
        current = model_display(ctx.conversation.model_id, default_suffix=True)
        return f"Current model: {current}\nSet one with `/model <id>`."
    model_id = ctx.args.strip()
    await update_conversation_model(
        conversation_id=ctx.conversation.id, model_id=model_id, session=ctx.session
    )
    return f"✅ Model set to {model_id} for this conversation."


async def _cmd_thinking(ctx: CommandContext) -> str:
    if not ctx.args:
        current = ctx.conversation.reasoning_effort or "provider default"
        return f"Current reasoning: {current}\nSet with `/thinking <{'|'.join(_REASONING_LEVELS)}|none>`."
    level = ctx.args.strip().lower()
    if level != _REASONING_CLEAR and level not in _REASONING_LEVELS:
        choices = ", ".join((*_REASONING_LEVELS, _REASONING_CLEAR))
        return f"Unknown level '{level}'. Choose one of: {choices}."
    stored = None if level == _REASONING_CLEAR else level
    await update_conversation_reasoning_effort(
        conversation_id=ctx.conversation.id,
        user_id=ctx.user_id,
        reasoning_effort=stored,
        session=ctx.session,
    )
    return f"✅ Reasoning effort set to {level}."


async def _cmd_verbose(ctx: CommandContext) -> str:
    if not ctx.args:
        current = _verbose_of(ctx.conversation)
        return (
            f"Current verbosity: {current} ({_VERBOSE_LABELS.get(current, '?')})\n"
            "Set with `/verbose <0|1|2>`."
        )
    raw = ctx.args.strip()
    if raw not in _VERBOSE_CHOICES:
        return "Verbosity must be 0 (quiet), 1 (tools), or 2 (thinking)."
    level = int(raw)
    await update_conversation_verbose_level(
        conversation_id=ctx.conversation.id, verbose_level=level, session=ctx.session
    )
    return f"✅ Verbosity set to {level} ({_VERBOSE_LABELS[level]})."


async def _cmd_config(ctx: CommandContext) -> str:
    workspace = await get_default_workspace(ctx.user_id, ctx.session)
    if workspace is None:
        return "No workspace yet — send a message first to set one up."
    root = Path(workspace.path)
    env = load_workspace_env(root)
    if not ctx.args:
        return config_status_text(env)
    return apply_config_toggle(root, env, ctx.args)


async def _cmd_lcm(ctx: CommandContext) -> str:
    return await lcm_status_text(conversation_id=ctx.conversation.id, session=ctx.session)


async def _cmd_compact(ctx: CommandContext) -> str:
    model_id = effective_model_id(conversation_model_id=ctx.conversation.model_id)
    return await run_compaction(
        conversation_id=ctx.conversation.id, user_id=ctx.user_id, model_id=model_id
    )


async def _cmd_stop(ctx: CommandContext) -> str:
    # The pull loop processes one message at a time, so there's no concurrent
    # run a separate /stop could cancel — be honest rather than pretend.
    return (
        "Pawrrtal handles one message at a time on Google Chat, so there's no "
        "separate run to stop. Use /new to start a fresh conversation."
    )


def config_status_text(env: dict[str, str]) -> str:
    """Render the current workspace toggle states from a decoded env dict."""
    lines = ["*Workspace config*"]
    for name, (key, label, default) in _CONFIG_TOGGLES.items():
        on = _env_bool(env.get(key), default)
        lines.append(f"• {label}: {'on' if on else 'off'}  — `/config {name} on|off`")
    return "\n".join(lines)


def apply_config_toggle(root: Path, env: dict[str, str], args: str) -> str:
    """Parse ``<toggle> <on|off>``, persist it to the workspace env, and confirm."""
    parts = args.split()
    if len(parts) != _CONFIG_TOGGLE_ARGS or parts[1].lower() not in {"on", "off"}:
        return "Usage: `/config <active_recall|search_workspace> <on|off>`"
    name, state = parts[0].lower(), parts[1].lower()
    toggle = _CONFIG_TOGGLES.get(name)
    if toggle is None:
        return f"Unknown toggle '{name}'. Choose: {', '.join(_CONFIG_TOGGLES)}."
    key, label, _default = toggle
    env[key] = "true" if state == "on" else "false"
    save_workspace_env(root, env)
    return f"✅ {label} set to {state}."


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


_HANDLERS: dict[str, Callable[[CommandContext], Awaitable[str]]] = {
    "help": _cmd_help,
    "new": _cmd_new,
    "whoami": _cmd_whoami,
    "status": _cmd_status,
    "model": _cmd_model,
    "thinking": _cmd_thinking,
    "verbose": _cmd_verbose,
    "config": _cmd_config,
    "lcm": _cmd_lcm,
    "compact": _cmd_compact,
    "stop": _cmd_stop,
}

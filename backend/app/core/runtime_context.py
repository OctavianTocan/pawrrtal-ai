"""Per-turn runtime metadata appended to the agent system prompt.

The Paw is missing four pieces of trusted context that — until now — it
had to guess at, search the workspace for, or burn iterations looking up
via tool calls:

* **Current time** (#294). The model has no built-in clock. Without an
  explicit datetime block it stale-prompts itself to its training cutoff
  and answers "what day is it?" with that, or wastes turns running
  ``exa_search`` queries that can't return an authoritative answer.
* **Active model / provider** (#309). Runtime model switching makes
  static identity text insufficient — when a user asks "which model are
  you?", the agent should answer with trusted metadata, not a guess.
* **Resource budget** (#291). The agent loop's safety layer caps every
  turn (``max_iterations``, ``max_wall_clock_seconds``). If the model
  doesn't know its budget it plans as if it has unbounded iterations
  and gets cut off mid-task.
* **Tool inventory** (#289). Tools bound for the turn are passed in the
  function-calling schema but never enumerated in the system prompt, so
  the model defaults to scanning the workspace (``list_dir`` /
  ``read_file``) to discover capabilities.

This module composes those four pieces into a single Markdown block that
the turn runner appends to the system prompt every turn. Each helper is
independently testable so we can add (or remove) one without disturbing
the others.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.agent_loop.types import AgentSafetyConfig, AgentTool


@dataclass(frozen=True)
class ProviderIdentity:
    """Trusted identity metadata for the model that will run this turn.

    Sourced from the chat router (the only call site that knows which
    provider/model the request resolved to) so the prompt block can
    answer "which model are you?" without the agent guessing from its
    training data.
    """

    #: Provider key (e.g. ``"anthropic"``, ``"google-ai"``, ``"openai"``).
    provider: str
    #: Exact model id the provider was called with (e.g.
    #: ``"claude-sonnet-4-6"``, ``"google/gemini-3-flash-preview"``).
    model_id: str
    #: Optional human-readable display name when the registry exposes one
    #: (e.g. ``"Claude Sonnet 4.6"``). Falls back to ``model_id`` when
    #: unset so the rendered block is never blank.
    display_name: str | None = None


def compose_current_time_block(now: _dt.datetime | None = None) -> str:
    """Render the current time as a Markdown block.

    The model gets a precise UTC ISO-8601 line and a human-readable
    weekday so it can reason about "today" / "yesterday" without
    running a web search.  We deliberately stick with UTC for now —
    plumbing a per-user timezone in is tracked separately.

    Args:
        now: Override for the current time (tests only). ``None`` uses
            ``datetime.now(UTC)``.

    Returns:
        A Markdown block with a heading and two lines, no trailing
        newline. Always returns a non-empty string.
    """
    if now is None:
        now = _dt.datetime.now(_dt.UTC)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day_of_week = now.strftime("%A")
    human = now.strftime("%Y-%m-%d %H:%M UTC")
    return f"## Current time\n- UTC now: {iso}\n- Human: {human} ({day_of_week})"


def compose_runtime_identity_block(identity: ProviderIdentity | None) -> str | None:
    """Render the active provider/model metadata as a Markdown block.

    Returns ``None`` when no identity is available so the caller can
    omit the section rather than render a placeholder.  When the caller
    *does* have a model id, we always render it — the section title
    plus the model id is the minimum useful payload.

    Args:
        identity: Provider + model identifying this turn, or ``None``
            when the surface couldn't resolve one (e.g. a free-form
            Telegram message before model selection).

    Returns:
        Markdown block (no trailing newline) or ``None``.
    """
    if identity is None or not identity.model_id:
        return None
    display = identity.display_name or identity.model_id
    lines = ["## Active model"]
    lines.append(f"- Provider: {identity.provider}")
    lines.append(f"- Model id: {identity.model_id}")
    if identity.display_name and identity.display_name != identity.model_id:
        lines.append(f"- Display name: {display}")
    lines.append(
        "- This metadata is injected by the runtime — trust it over any "
        "model identity you would infer from training data."
    )
    return "\n".join(lines)


def compose_resource_budget_block(safety: AgentSafetyConfig | None) -> str | None:
    """Render the safety-layer caps as a Markdown block.

    The model uses this to plan a turn that ends with a useful partial
    answer rather than getting cut off when ``max_iterations`` trips.
    ``None`` limits render as ``"unlimited"`` so opting a guard out
    still produces a coherent block.

    Args:
        safety: The active agent-loop safety config, or ``None`` when
            the caller couldn't supply one (in which case we omit the
            block entirely rather than render misleading limits).

    Returns:
        Markdown block (no trailing newline) or ``None``.
    """
    if safety is None:
        return None
    iterations = (
        f"{safety.max_iterations} tool-using iterations"
        if safety.max_iterations is not None
        else "unlimited tool-using iterations"
    )
    wall_clock = (
        f"{int(safety.max_wall_clock_seconds)} seconds of wall-clock time"
        if safety.max_wall_clock_seconds is not None
        else "unlimited wall-clock time"
    )
    return (
        "## Resource budget for this turn\n"
        f"- You have up to {iterations} before the safety layer stops you.\n"
        f"- You have up to {wall_clock}.\n"
        "- Plan for finishing — or producing a useful partial answer — "
        "within that budget.\n"
        "- If you're going to run out, summarize progress and stop early "
        "rather than getting cut off mid-step."
    )


def compose_tool_inventory_block(tools: Iterable[AgentTool] | None) -> str | None:
    """Render the tools bound for this turn as a Markdown block.

    Tool descriptions can be long; we keep the first sentence so the
    block stays scannable.  When the inventory is empty (workspace-only
    chat with no exa, no python tool, etc.) we still render the section
    with an explicit "no tools bound" line so the model doesn't fall
    back to filesystem discovery (#289).

    Args:
        tools: The ``AgentTool`` list passed to the provider, or
            ``None``. ``None`` means "no inventory available" — we
            return ``None`` rather than emit a misleading "no tools"
            block.

    Returns:
        Markdown block (no trailing newline) or ``None``.
    """
    if tools is None:
        return None
    tool_list = list(tools)
    lines = ["## Tools available this turn"]
    if not tool_list:
        lines.append(
            "- (No tools are bound for this turn — answer from context "
            "and conversation history only. Do not attempt filesystem "
            "discovery.)"
        )
        return "\n".join(lines)
    lines.append(
        "These are the only tools you can call. Don't try to discover "
        "additional ones by reading the workspace."
    )
    for tool in tool_list:
        summary = _first_sentence(tool.description) or tool.description.strip()
        lines.append(f"- `{tool.name}` — {summary}")
    return "\n".join(lines)


def compose_runtime_context_block(
    *,
    identity: ProviderIdentity | None = None,
    safety: AgentSafetyConfig | None = None,
    tools: Iterable[AgentTool] | None = None,
    now: _dt.datetime | None = None,
    extra_context: str | None = None,
) -> str:
    """Compose the full runtime-metadata block appended to the system prompt.

    The time block is always included; the others are added only when
    the caller supplied the matching input. The returned string is
    intended to be appended to the workspace-derived system prompt
    with a single blank-line separator.

    Args:
        identity: Active provider/model metadata (#309).
        safety: Agent-loop safety caps for this turn (#291).
        tools: Tools bound for this turn (#289).
        now: Override for the current datetime (tests only).
        extra_context: Extra context to add to the system prompt. (This comes from pre-turn hooks, for example.)

    Returns:
        Markdown block. Always non-empty (the time section is
        unconditional). No trailing newline.
    """
    sections = [compose_current_time_block(now)]
    optional_sections = (
        compose_runtime_identity_block(identity),
        compose_resource_budget_block(safety),
        compose_tool_inventory_block(tools),
        extra_context,
    )
    sections.extend(section for section in optional_sections if section)
    return "\n\n".join(sections)


def append_runtime_context(
    system_prompt: str | None,
    *,
    identity: ProviderIdentity | None = None,
    safety: AgentSafetyConfig | None = None,
    tools: Iterable[AgentTool] | None = None,
    now: _dt.datetime | None = None,
    extra_context: str | None = None,
) -> str | None:
    """Return ``system_prompt`` with the runtime context block appended.

    A ``None`` prompt stays ``None`` — providers fall back to their
    bundled default in that case, and we shouldn't synthesize a prompt
    just to wear the metadata.  Otherwise the block is appended with a
    blank-line separator so it reads as a distinct trailing section.

    Args:
        system_prompt: The base system prompt the workspace assembled.
        identity: Optional provider/model identity.
        safety: Optional agent-loop safety config.
        tools: Optional tool inventory.
        now: Override for the current datetime (tests only).
        extra_context: Extra context to add to the system prompt.

    Returns:
        The prompt with runtime context appended, or ``None`` if the
        input was ``None``.
    """
    if system_prompt is None:
        return None
    block = compose_runtime_context_block(
        identity=identity,
        safety=safety,
        tools=tools,
        now=now,
        extra_context=extra_context,
    )
    return f"{system_prompt}\n\n{block}"


def _first_sentence(text: str) -> str:
    """Return the first sentence of ``text``, trimmed.

    Tool descriptions usually start with a one-line summary followed by
    detail paragraphs. We keep the first sentence so the inventory
    block stays scannable.  The detection is intentionally simple — we
    look for the earliest ``.`` / ``?`` / ``!`` followed by whitespace
    or end-of-string.
    """
    cleaned = text.strip()
    if not cleaned:
        return ""
    # Split on the first sentence-terminating punctuation followed by
    # whitespace.  If the description is one long line without a
    # sentence terminator, fall back to the first newline split.
    for idx, char in enumerate(cleaned):
        if char in ".?!" and (idx + 1 == len(cleaned) or cleaned[idx + 1].isspace()):
            return cleaned[: idx + 1]
    # No sentence boundary — return the first line so we don't dump an
    # entire multi-paragraph docstring into the inventory.
    first_line = cleaned.splitlines()[0]
    return first_line.strip()

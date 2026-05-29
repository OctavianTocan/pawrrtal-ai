"""History and input translation for the openai_codex provider.

This module is responsible for converting Pawrrtal's conversation history
(the list of message dicts passed to `provider.stream(...)`) plus the current
user question, images, and system prompt into the input shapes expected by
the official Codex Python SDK (`TextInput`, `ImageInput`, `RunInput`, etc.).

Design goals for a *full clean* integration:
- Preserve as much context as possible (previous assistant messages,
  reasoning summaries when available, tool results).
- Support multimodal input (images) cleanly.
- Stay small, focused, and well under the 500-line file budget.
- Provide a clear extension point for richer item types as the SDK evolves
  (e.g. injecting previous reasoning blocks for true continuity).

The SDK itself prefers long-lived `Thread` objects for true multi-turn
continuity (`thread_resume` + persisted `thread_id`). This module is the
translation layer used when we still need to send history explicitly
(e.g. on a fresh thread or when doing explicit replay).

Public API (used by the provider orchestrator):

    from .inputs import build_codex_run_input

    codex_input = build_codex_run_input(
        question=question,
        history=history,
        system_prompt=system_prompt,
        images=images,
    )
"""

from __future__ import annotations

import logging
from typing import Any

# Ensure the openai_codex SDK is on sys.path before we import from it.
# This module is only loaded when the provider needs to build a Codex
# turn input, which is well after any cold-import concern. We translate
# the vendor bootstrap's RuntimeError into ImportError so that callers
# (and import-isolation tests) see the same exception type they'd see
# from a missing package.
from ._vendor import ensure_openai_codex_available

try:
    ensure_openai_codex_available()
except RuntimeError as exc:
    raise ImportError(str(exc)) from exc

from openai_codex import (
    ImageInput,
    InputItem,
    LocalImageInput,
    RunInput,
    TextInput,
)

logger = logging.getLogger(__name__)


def _message_to_input_items(msg: dict[str, Any]) -> list[InputItem]:
    """Convert a single Pawrrtal message dict into zero or more InputItems.

    Pawrrtal message shape (simplified):
        {
            "role": "user" | "assistant" | "system" | "tool",
            "content": str | None,
            "thinking": str | None,           # reasoning summary / raw
            "tool_calls": [...],              # if any
            "tool_call_id": str | None,
            ...
        }
    """
    role = (msg.get("role") or "").lower()
    content = msg.get("content") or ""
    thinking = msg.get("thinking")
    tool_calls = msg.get("tool_calls") or []
    tool_call_id = msg.get("tool_call_id")

    items: list[InputItem] = []

    # Tool results (from previous tool execution)
    if role == "tool" and tool_call_id:
        # The SDK surface for tool outputs is still evolving in the high-level
        # API. For now we replay the tool result as context text.
        # A future _tool_bridge will do proper function call result injection.
        text = f"[Tool result for {tool_call_id}] {content}".strip()
        if text:
            items.append(TextInput(text=text))
        return items

    # User messages (including the current question)
    if role in ("user", "human"):
        if content:
            items.append(TextInput(text=content))
        return items

    # Assistant messages (previous turns)
    if role in ("assistant", "ai", "model"):
        # Replay previous assistant output so the model has context.
        # We prefix it lightly so the model understands this is history.
        if thinking:
            # Previous reasoning summary is valuable context
            items.append(
                TextInput(
                    text=f"[Previous assistant reasoning]\n{thinking}\n\n"
                    f"[Previous assistant response]\n{content}"
                )
            )
        elif content:
            items.append(TextInput(text=f"[Previous assistant response]\n{content}"))

        # Tool calls the assistant made in the past (replayed as context)
        for tc in tool_calls:
            name = tc.get("name", "unknown_tool")
            args = tc.get("arguments", {})
            items.append(TextInput(text=f"[Previous assistant tool call] {name}({args})"))

        return items

    # System / developer instructions are usually passed via
    # `base_instructions` on thread_start rather than as InputItems.
    if role == "system":
        # We ignore it here; the provider passes it at thread creation time.
        return items

    # Unknown roles — best effort
    if content:
        items.append(TextInput(text=content))

    return items


def build_codex_run_input(
    question: str,
    history: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
    images: list[dict[str, str]] | None = None,
) -> RunInput:
    """Convert a Pawrrtal turn (history + question + images) into a Codex ``RunInput``.

    Returns either a plain string or a list of ``InputItem``.

    This is the main entry point used by `OpenAICodexProvider`.

    For the highest quality experience we try to build a rich list of
    `InputItem`s that includes previous context. The official SDK has
    excellent support for this.

    Args:
        question: The current user question.
        history: Previous messages in Pawrrtal format (role/content/thinking/etc.).
        system_prompt: Optional system/developer instructions (usually passed
            via `base_instructions` on thread_start instead).
        images: Optional list of image dicts (`{"url": ...}` or `{"path": ...}`).

    Returns:
        A `RunInput` ready to be passed to `thread.turn(...)` or `thread.run(...)`.
    """
    items: list[InputItem] = []

    # 1. Replay conversation history (if any)
    if history:
        for msg in history:
            try:
                items.extend(_message_to_input_items(msg))
            except Exception as exc:
                logger.debug("openai_codex.inputs: failed to translate history msg: %s", exc)

    # 2. Current user question (always last)
    if question:
        items.append(TextInput(text=question))

    # 3. Attached images for this turn
    for img in images or []:
        try:
            if "url" in img:
                items.append(ImageInput(url=img["url"]))
            elif "path" in img:
                items.append(LocalImageInput(path=img["path"]))
        except Exception as exc:
            logger.warning("openai_codex.inputs: failed to add image: %s", exc)

    # If we only have the current question (no history, no images),
    # the SDK accepts a plain string. Keep it simple.
    if len(items) == 1 and isinstance(items[0], TextInput):
        return items[0].text

    # Otherwise return the full list of items.
    return items if items else question


# Convenience alias used internally by the provider
normalize_run_input = build_codex_run_input

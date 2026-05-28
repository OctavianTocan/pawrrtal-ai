"""xAI request-shape helpers — AgentMessage → ``chat_pb2`` proto messages.

Pure shape translation between Pawrrtal's provider-neutral
:class:`AgentMessage` shape and xAI's gRPC ``Message`` / ``Tool``
protos.  No I/O, no client construction — the live :class:`AsyncClient`
lives in ``xai_provider``.

The xai-sdk ships ergonomic helpers (:func:`xai_sdk.chat.system`,
``user``, ``tool_result``, ``tool``, ``text``) that we use everywhere
they apply.  Assistant turns that carry tool calls fall back to direct
``chat_pb2`` construction because the SDK's ``assistant()`` helper only
takes textual ``Content`` and not ``tool_calls`` — see
https://github.com/xai-org/xai-sdk-python/blob/main/src/xai_sdk/chat.py
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from xai_sdk.chat import image as xai_image
from xai_sdk.chat import text, tool, tool_result, user
from xai_sdk.proto import chat_pb2

from app.core.agent_loop.types import (
    AgentMessage,
    AgentTool,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
)


def build_xai_tools(tools: list[AgentTool]) -> Sequence[chat_pb2.Tool] | None:
    """Convert :class:`AgentTool` instances to xAI ``Tool`` proto messages.

    Returns ``None`` (not ``[]``) when there are no tools so the caller
    can pass ``None`` to ``chat.create(tools=...)`` and let the SDK omit
    the field entirely from the wire request.
    """
    if not tools:
        return None
    return [tool(name=t.name, description=t.description, parameters=t.parameters) for t in tools]


def build_xai_messages(
    messages: list[AgentMessage],
    system_prompt: str,
    images: list[dict[str, str]] | None = None,
) -> list[chat_pb2.Message]:
    """Convert AgentMessages to xAI proto ``Message`` instances, oldest-first.

    The system prompt is rendered as a ``ROLE_DEVELOPER`` message —
    xAI's modern role for system instructions on grok-4.1+ — which the
    server downgrades to ``ROLE_SYSTEM`` for older models.  See the
    helper's docstring in xai-sdk's ``chat.py``.

    Per-message conversions:

    * ``user`` → :func:`xai_sdk.chat.user` (text/multimodal; empty turns are
      dropped to match the historical behaviour).
    * ``assistant`` → either :func:`xai_sdk.chat.text` for pure-text
      replies or a direct ``chat_pb2.Message`` carrying ``tool_calls``
      built from the loop's :class:`ToolCallContent` blocks.
    * ``toolResult`` → :func:`xai_sdk.chat.tool_result` so the SDK
      attaches the matching ``tool_call_id`` and ``ROLE_TOOL``.
    """
    # ``developer`` is the canonical xAI role for system instructions
    # on current models; older models silently see it as ``system``.
    out: list[chat_pb2.Message] = [
        chat_pb2.Message(
            role=chat_pb2.MessageRole.ROLE_DEVELOPER,
            content=[text(system_prompt)],
        )
    ]

    last_user_idx = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            last_user_idx = idx

    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            user_text = msg["content"]
            if idx == last_user_idx and images:
                content_args = []
                if user_text.strip():
                    content_args.append(user_text)
                for img in images:
                    if "data" in img:
                        media_type = img.get("media_type", "image/png")
                        data_uri = f"data:{media_type};base64,{img['data']}"
                        content_args.append(xai_image(data_uri))
                if content_args:
                    out.append(user(*content_args))
            elif user_text.strip():
                out.append(user(user_text))
            continue
        if msg["role"] == "assistant":
            out.append(_assistant_proto(msg["content"]))
            continue
        # toolResult.
        out.append(_tool_result_proto(msg))
    return out


def _assistant_proto(
    content: list[TextContent | ToolCallContent],
) -> chat_pb2.Message:
    """Render an assistant turn into a ``chat_pb2.Message`` with tool calls.

    The xai-sdk helper :func:`xai_sdk.chat.assistant` only takes
    ``Content`` (text / image / file) and does not expose ``tool_calls``,
    so we construct the proto directly to preserve the agent loop's
    tool-call history across iterations.  When the turn has only tool
    calls and no text, a single empty ``text("")`` element is included
    because the xAI server requires at least one content element per
    message (gRPC ``AioRpcError`` otherwise).
    """
    text_parts: list[str] = []
    tool_calls: list[chat_pb2.ToolCall] = []
    for block in content:
        if block["type"] == "text":
            text_parts.append(block["text"])
            continue
        tool_calls.append(
            chat_pb2.ToolCall(
                id=block["tool_call_id"],
                function=chat_pb2.FunctionCall(
                    name=block["name"],
                    arguments=json.dumps(block["arguments"]),
                ),
            )
        )
    combined = "".join(text_parts)
    proto_content = [text(combined)] if combined else [text("")]
    return chat_pb2.Message(
        role=chat_pb2.MessageRole.ROLE_ASSISTANT,
        content=proto_content,
        tool_calls=tool_calls,
    )


def _tool_result_proto(msg: ToolResultMessage) -> chat_pb2.Message:
    """Render a loop ``toolResult`` into the SDK's ``tool_result`` helper output.

    The xai-sdk helper attaches the ``tool_call_id`` and sets
    ``ROLE_TOOL`` correctly, so we just join the agent loop's
    multi-block result text into one string and delegate.
    """
    body = "\n".join(b["text"] for b in msg["content"])
    return tool_result(body, tool_call_id=msg["tool_call_id"])

"""Cloud Code Assist message and tool-shape helpers for Antigravity."""

from __future__ import annotations

from typing import Any

from app.agents.types import (
    AgentMessage,
    AgentTool,
    AssistantMessage,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)
from app.providers.base import ReasoningEffort

_EFFORT_TO_THINKING_LEVEL: dict[ReasoningEffort, str] = {
    "minimal": "LOW",
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
    "extra-high": "HIGH",
}

_MODEL_THINKING_BUDGETS: dict[str, int] = {
    "gemini-3.5-flash-extra-low": 1000,
    "gemini-3.5-flash-low": 4000,
    "claude-sonnet-4-6": 1024,
    "gemini-2.5-pro": 1024,
    "gemini-3.1-pro-low": 1001,
    "gpt-oss-120b-medium": 8192,
    "claude-opus-4-6-thinking": 1024,
    "gemini-pro-agent": 10001,
    "gemini-3-flash-agent": 10000,
    "gemini-3.1-pro-high": 10001,
}


def build_agy_contents(messages: list[AgentMessage]) -> list[dict[str, Any]]:
    """Convert Pawrrtal agent messages to Gemini-style REST contents."""
    contents: list[dict[str, Any]] = []
    for msg in messages:
        if msg["role"] == "user":
            content = _user_content(msg)
            if content is not None:
                contents.append(content)
            continue
        if msg["role"] == "assistant":
            content = _assistant_content(msg)
            if content is not None:
                contents.append(content)
            continue
        contents.append(_tool_result_content(msg))
    return contents


def build_agy_tool_declarations(tools: list[AgentTool]) -> list[dict[str, Any]] | None:
    """Convert AgentTools to Cloud Code Assist function declarations."""
    if not tools:
        return None
    return [
        {
            "functionDeclarations": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in tools
            ]
        }
    ]


def build_agy_generation_config(
    *,
    model_id: str | None = None,
    reasoning_effort: ReasoningEffort | None,
) -> dict[str, Any]:
    """Build generationConfig with thinking enabled when possible."""
    thinking_config: dict[str, Any] = {"includeThoughts": True}
    budget = _MODEL_THINKING_BUDGETS.get(model_id or "")
    if budget is not None:
        thinking_config["thinkingBudget"] = budget
    elif reasoning_effort is not None:
        thinking_config["thinkingLevel"] = _EFFORT_TO_THINKING_LEVEL[reasoning_effort]
    return {"thinkingConfig": thinking_config}


def _user_content(msg: UserMessage) -> dict[str, Any] | None:
    text = msg["content"]
    if not text.strip():
        return None
    return {"role": "user", "parts": [{"text": text}]}


def _assistant_content(msg: AssistantMessage) -> dict[str, Any] | None:
    replay = _replay_content(msg)
    if replay is not None:
        return replay
    parts = _assistant_parts(msg["content"])
    if not parts:
        return None
    return {"role": "model", "parts": parts}


def _assistant_parts(content: list[TextContent | ToolCallContent]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for block in content:
        if block["type"] == "text":
            text = block["text"]
            if text.strip():
                parts.append({"text": text})
            continue
        function_call: dict[str, Any] = {
            "name": block["name"],
            "args": block["arguments"],
        }
        if block["tool_call_id"]:
            function_call["id"] = block["tool_call_id"]
        parts.append({"functionCall": function_call})
    return parts


def _tool_result_content(msg: ToolResultMessage) -> dict[str, Any]:
    text = "\n".join(block["text"] for block in msg["content"])
    response_key = "error" if msg["is_error"] else "result"
    return {
        "role": "user",
        "parts": [
            {
                "functionResponse": {
                    "name": msg["name"],
                    "id": msg["tool_call_id"],
                    "response": {response_key: text},
                }
            }
        ],
    }


def _replay_content(msg: AssistantMessage) -> dict[str, Any] | None:
    provider_state = msg.get("provider_state")
    if not isinstance(provider_state, dict):
        return None
    agy_state = provider_state.get("agy_api")
    if not isinstance(agy_state, dict):
        return None
    model_content = agy_state.get("model_content")
    if not isinstance(model_content, dict):
        return None
    return model_content

"""Pi-inspired provider-agnostic agent loop."""

from __future__ import annotations

from .loop import agent_loop
from .system_prompt import (
    DEFAULT_AGENT_SYSTEM_PROMPT,
    PAW_CORE_SYSTEM_PROMPT,
    compose_agent_system_prompt,
)
from .types import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentSafetyConfig,
    AgentTerminatedEvent,
    AgentTool,
    AssistantMessage,
    LLMDoneEvent,
    LLMEvent,
    LLMTextDeltaEvent,
    LLMThinkingDeltaEvent,
    LLMToolCallEvent,
    StreamFn,
    ToolResultMessage,
    UserMessage,
)

__all__ = [
    "DEFAULT_AGENT_SYSTEM_PROMPT",
    "PAW_CORE_SYSTEM_PROMPT",
    "AgentContext",
    "AgentEvent",
    "AgentLoopConfig",
    "AgentMessage",
    "AgentSafetyConfig",
    "AgentTerminatedEvent",
    "AgentTool",
    "AssistantMessage",
    "LLMDoneEvent",
    "LLMEvent",
    "LLMTextDeltaEvent",
    "LLMThinkingDeltaEvent",
    "LLMToolCallEvent",
    "StreamFn",
    "ToolResultMessage",
    "UserMessage",
    "agent_loop",
    "compose_agent_system_prompt",
]

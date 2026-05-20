"""Claude Agent SDK provider package.

Wraps the Claude Code CLI (via :mod:`claude_agent_sdk`) and exposes a
streaming chat interface that matches the rest of the
:class:`app.core.providers.base.AILLM` protocol.

External callers only need the names re-exported below; everything
else is package-internal. The underscore-prefixed helpers are
intentionally part of the public package surface so the existing
test suite — which reaches in to assert specific helpers — keeps
working without churn while the implementation can split further
behind the scenes.
"""

from app.core.providers.claude.events import (
    _error_event as _error_event,
)
from app.core.providers.claude.events import (
    _events_from_assistant as _events_from_assistant,
)
from app.core.providers.claude.events import (
    _events_from_message as _events_from_message,
)
from app.core.providers.claude.events import (
    _tool_result_event as _tool_result_event,
)
from app.core.providers.claude.events import (
    _tool_result_to_text as _tool_result_to_text,
)
from app.core.providers.claude.history import _render_history_prefix as _render_history_prefix
from app.core.providers.claude.prompt import _aiter_user_prompt as _aiter_user_prompt
from app.core.providers.claude.provider import (
    ClaudeLLM as ClaudeLLM,
)
from app.core.providers.claude.provider import (
    ClaudeLLMConfig as ClaudeLLMConfig,
)
from app.core.providers.claude.provider import (
    _resolve_sdk_model as _resolve_sdk_model,
)
from app.core.providers.claude.provider import (
    _session_exists as _session_exists,
)
from app.core.providers.claude.retry import (
    _is_retryable_cli_connection as _is_retryable_cli_connection,
)
from app.core.providers.claude.retry import (
    _retry_backoff_seconds as _retry_backoff_seconds,
)

__all__ = [
    "ClaudeLLM",
    "ClaudeLLMConfig",
    "_aiter_user_prompt",
    "_error_event",
    "_events_from_assistant",
    "_events_from_message",
    "_is_retryable_cli_connection",
    "_render_history_prefix",
    "_resolve_sdk_model",
    "_retry_backoff_seconds",
    "_session_exists",
    "_tool_result_event",
    "_tool_result_to_text",
]

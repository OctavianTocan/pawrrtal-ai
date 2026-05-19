"""Pawrrtal-side ACP client that drives the Gemini CLI subprocess.

Implements the :class:`acp.Client` protocol so the Gemini CLI subprocess
(spawned with ``gemini --acp``) can stream notifications back to us and
request permission, file system access, or terminal commands.

The class is intentionally narrow: it only translates ACP
``session/update`` notifications into Pawrrtal :class:`StreamEvent`
records pushed onto an :class:`asyncio.Queue`, plus a tiny bit of
glue for filesystem + permission requests. The owning
:class:`gemini_cli_provider.GeminiCliLLM` drains the queue and yields
the events to the chat router.

The asymmetry of "agent calls back into client" maps to Pawrrtal's
existing seams:

* ``session_update`` notifications → :class:`StreamEvent` on the queue
  (consumed by the chat aggregator + SSE encoder).
* ``request_permission`` requests → optional cross-provider
  :data:`PermissionCheckFn` (the same closure Claude consumes via
  ``can_use_tool`` and our internal Gemini SDK provider consumes via
  ``AgentLoopConfig.permission_check``). When no closure is supplied,
  we auto-approve — the user explicitly opted into a local CLI
  backend, so the default is "trust it".
* ``fs/read_text_file`` / ``fs/write_text_file`` → scoped to
  ``workspace_root``. Paths outside the workspace are rejected with
  ``RequestError.invalid_params`` so the model self-corrects rather
  than silently reading host files.
* Terminal methods are declared unsupported via the ``initialize``
  capability negotiation, but kept here as ``method_not_found``
  raises in case the agent calls them anyway (defence in depth).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from acp import RequestError
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AllowedOutcome,
    AvailableCommandsUpdate,
    ConfigOptionUpdate,
    CreateTerminalResponse,
    CurrentModeUpdate,
    DeniedOutcome,
    EmbeddedResourceContentBlock,
    EnvVariable,
    FileEditToolCallContent,
    ImageContentBlock,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    ResourceContentBlock,
    SessionInfoUpdate,
    TerminalOutputResponse,
    TerminalToolCallContent,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    UserMessageChunk,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

from app.core.agent_loop.types import PermissionCheckFn

from .base import StreamEvent

logger = logging.getLogger(__name__)


PermissionOptionKind = str
"""ACP permission option kinds — ``allow_once``, ``allow_always``,
``reject_once``, ``reject_always``. We model as ``str`` rather than a
literal alias to track upstream changes without redefining."""

ALLOW_KINDS: frozenset[PermissionOptionKind] = frozenset({"allow_once", "allow_always"})
"""Permission option kinds we treat as "approve" when auto-approving.
Anything else (rejection, cancellation) we leave alone — picking the
first matching allow option keeps the lifetime narrow (``allow_once``
beats ``allow_always`` when both are offered)."""

_DENY_OUTCOME = "cancelled"
"""ACP ``DeniedOutcome`` requires a string — ``cancelled`` is the
spec's standard value for "client refused the option list"."""

_ALLOW_OUTCOME = "selected"
"""ACP ``AllowedOutcome`` requires a string — ``selected`` is the
spec's standard value for "client picked one of the options"."""


def pick_allow_option(options: list[PermissionOption]) -> PermissionOption | None:
    """Return the most-restrictive allow option, or ``None`` if none exist.

    ``allow_once`` is preferred over ``allow_always`` so an
    auto-approved decision does not silently widen future permission
    scope. When no allow options exist (only reject/cancel), the caller
    should treat that as a denial.
    """
    once: PermissionOption | None = None
    always: PermissionOption | None = None
    for option in options:
        if option.kind == "allow_once" and once is None:
            once = option
        elif option.kind == "allow_always" and always is None:
            always = option
    return once or always


def text_from_content_block(block: object) -> str:
    """Extract text content from any ACP content block, best-effort.

    Returns the empty string for blocks that carry no displayable text
    (audio, binary resources). Used to fold Gemini's streamed
    ``AgentMessageChunk`` payloads into the ``StreamEvent(type="delta")``
    string the chat aggregator + SSE encoder expect.
    """
    if isinstance(block, TextContentBlock):
        return block.text
    if isinstance(block, ImageContentBlock):
        return ""
    if isinstance(block, ResourceContentBlock):
        return block.name or block.uri or ""
    if isinstance(block, EmbeddedResourceContentBlock):
        resource = block.resource
        text_attr = getattr(resource, "text", None)
        return text_attr if isinstance(text_attr, str) else ""
    return ""


def text_from_tool_content_item(item: object) -> str:
    """Render one tool-call content variant as the text we surface to the UI."""
    if isinstance(item, FileEditToolCallContent):
        return f"diff: {item.path}"
    if isinstance(item, TerminalToolCallContent):
        return f"terminal: {item.terminal_id}"
    # ``ContentToolCallContent`` wraps another content block.
    inner = getattr(item, "content", None)
    if inner is not None:
        return text_from_content_block(inner)
    return ""


class PawrrtalAcpClient:
    """ACP :class:`Client` implementation that bridges Gemini CLI → Pawrrtal.

    All inbound traffic from the agent (``session/update`` notifications,
    permission requests, file system requests) flows through methods on
    this class. ``session_update`` pushes :class:`StreamEvent` records
    onto the queue the owning provider drains; the rest is request/reply
    bridging to Pawrrtal's existing primitives.
    """

    def __init__(
        self,
        *,
        event_queue: asyncio.Queue[StreamEvent | None],
        workspace_root: Path | None,
        permission_check: PermissionCheckFn | None,
    ) -> None:
        """Construct the client.

        Args:
            event_queue: Sink for translated :class:`StreamEvent` records.
                The provider closes the queue with ``None`` once the
                prompt turn finishes; this class never closes it.
            workspace_root: Absolute path the agent's filesystem
                operations are scoped to. When ``None`` the agent should
                not have filesystem capability declared in
                ``initialize``; this is asserted as a defence-in-depth
                check at request time.
            permission_check: Optional cross-provider permission gate.
                When supplied, ``request_permission`` consults it before
                approving any tool. When ``None``, every permission is
                auto-approved (the user opted into a local CLI agent —
                the trust model is "you trust your local agent").
        """
        self._event_queue = event_queue
        self._workspace_root = workspace_root
        self._permission_check = permission_check

    async def session_update(
        self,
        session_id: str,
        update: UserMessageChunk
        | AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress
        | AgentPlanUpdate
        | AvailableCommandsUpdate
        | CurrentModeUpdate
        | ConfigOptionUpdate
        | SessionInfoUpdate
        | UsageUpdate,
        **kwargs: Any,
    ) -> None:
        """Translate an ACP session update into a Pawrrtal StreamEvent."""
        event = _stream_event_for_update(update)
        if event is not None:
            await self._event_queue.put(event)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        """Approve or deny a tool-call permission request."""
        if self._permission_check is not None:
            tool_name = tool_call.title or "<unknown>"
            arguments = tool_call.raw_input if isinstance(tool_call.raw_input, dict) else {}
            decision = await self._permission_check(tool_name, arguments)
            if not decision["allow"]:
                logger.info(
                    "GEMINI_CLI_PERMISSION_DENIED tool=%s reason=%s",
                    tool_name,
                    decision["reason"],
                )
                return RequestPermissionResponse(outcome=DeniedOutcome(outcome=_DENY_OUTCOME))
        option = pick_allow_option(options)
        if option is None:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome=_DENY_OUTCOME))
        return RequestPermissionResponse(
            outcome=AllowedOutcome(option_id=option.option_id, outcome=_ALLOW_OUTCOME),
        )

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        """Read a workspace-scoped file for the agent."""
        resolved = _ensure_workspace_path(path, self._workspace_root)
        text = resolved.read_text()
        if line is not None or limit is not None:
            text = _slice_text(text, line, limit)
        return ReadTextFileResponse(content=text)

    async def write_text_file(
        self,
        content: str,
        path: str,
        session_id: str,
        **kwargs: Any,
    ) -> WriteTextFileResponse | None:
        """Write a workspace-scoped file on the agent's behalf."""
        resolved = _ensure_workspace_path(path, self._workspace_root)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return WriteTextFileResponse()

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        """Terminals are not exposed to the agent."""
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Reject custom extension methods we did not opt into."""
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Ignore custom extension notifications we do not handle."""
        logger.debug("GEMINI_CLI_EXT_NOTIFICATION_IGNORED method=%s", method)

    def on_connect(self, conn: object) -> None:
        """Hook fired once the connection is established. No-op for us."""


# ---------------------------------------------------------------------------
# Module-level helpers (also unit-tested directly).
# ---------------------------------------------------------------------------


def _stream_event_for_update(update: object) -> StreamEvent | None:
    """Map one ACP session-update variant to a Pawrrtal StreamEvent."""
    if isinstance(update, AgentMessageChunk):
        text = text_from_content_block(update.content)
        return StreamEvent(type="delta", content=text) if text else None
    if isinstance(update, AgentThoughtChunk):
        text = text_from_content_block(update.content)
        return StreamEvent(type="thinking", content=text) if text else None
    if isinstance(update, ToolCallStart):
        return _tool_start_event(update)
    if isinstance(update, ToolCallProgress):
        return _tool_progress_event(update)
    if isinstance(update, UsageUpdate):
        return _usage_event(update)
    # Plan, available-commands, mode-change, config-option, session-info,
    # user-message-chunk: not surfaced as StreamEvents in v1. They are
    # editor-UI hints (mode badges, slash-command palettes) that have no
    # equivalent in Pawrrtal's chat surface yet.
    return None


def _tool_start_event(update: ToolCallStart) -> StreamEvent:
    """Translate a ``tool_call`` notification to ``StreamEvent(type=tool_use)``."""
    raw_input = update.raw_input if isinstance(update.raw_input, dict) else {}
    return StreamEvent(
        type="tool_use",
        name=update.kind or update.title or "tool",
        input=raw_input,
        tool_use_id=update.tool_call_id,
    )


def _tool_progress_event(update: ToolCallProgress) -> StreamEvent | None:
    """Translate a ``tool_call_update`` notification.

    Only terminal statuses (``completed`` / ``failed``) become user-visible
    ``tool_result`` events; intermediate progress is dropped since the
    chat aggregator already shows a spinner from the ``tool_use`` event.
    """
    if update.status not in {"completed", "failed"}:
        return None
    pieces: list[str] = []
    for item in update.content or []:
        text = text_from_tool_content_item(item)
        if text:
            pieces.append(text)
    body = "\n".join(pieces)
    if update.status == "failed" and not body:
        body = "<tool failed>"
    return StreamEvent(
        type="tool_result",
        content=body,
        tool_use_id=update.tool_call_id,
    )


def _usage_event(update: UsageUpdate) -> StreamEvent | None:
    """Translate a ``usage`` notification into ``StreamEvent(type=usage)``.

    ACP's ``UsageUpdate`` reports the *current* context window state
    (``size`` total, ``used`` consumed) rather than per-turn token deltas.
    Until Pawrrtal's cost ledger learns to consume that shape directly,
    surface only the values that match the existing ``StreamEvent``
    contract (input / output / cost). When the SDK exposes the per-turn
    breakdown via ``cost``, this becomes the place to translate it.
    """
    cost_blob = getattr(update, "cost", None)
    if cost_blob is None:
        return None
    cost_usd = getattr(cost_blob, "total_cost_usd", None)
    if cost_usd is None:
        return None
    return StreamEvent(type="usage", cost_usd=float(cost_usd))


def _ensure_workspace_path(path: str, workspace_root: Path | None) -> Path:
    """Validate ``path`` is an absolute path under ``workspace_root``.

    The Gemini CLI's filesystem methods only carry absolute paths per
    the ACP spec, so the absolute check would normally pass; we keep
    it explicit because a non-absolute path from a buggy agent could
    otherwise be resolved against ``Path.cwd()`` and escape the
    workspace via traversal.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        raise RequestError.invalid_params(
            {"path": path, "reason": "path must be absolute"},
        )
    if workspace_root is None:
        raise RequestError.invalid_params(
            {"path": path, "reason": "filesystem access not enabled for this session"},
        )
    resolved = candidate.resolve()
    workspace_resolved = workspace_root.resolve()
    if not resolved.is_relative_to(workspace_resolved):
        raise RequestError.invalid_params(
            {"path": path, "reason": "path is outside the workspace"},
        )
    return resolved


def _slice_text(content: str, line: int | None, limit: int | None) -> str:
    """Return ``content`` sliced by 1-based ``line`` / ``limit`` lines.

    Mirrors the ACP spec's read_text_file semantics: ``line`` is the
    1-based starting line, ``limit`` caps the number of returned lines.
    Out-of-range values are clamped (the spec leaves clamping to the
    client; clamping is forgiving so the model self-corrects on the
    next read instead of erroring).
    """
    lines = content.splitlines()
    start = max((line or 1) - 1, 0)
    end = len(lines)
    if limit is not None:
        end = min(start + limit, end)
    return "\n".join(lines[start:end])

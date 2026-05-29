"""Pawrrtal-side ACP client that drives the Gemini CLI subprocess.

Implements the :class:`acp.Client` protocol so the Gemini CLI subprocess
(spawned with ``gemini --acp``) can stream notifications back to us and
request permission, file system access, or terminal commands.

The class is intentionally narrow: it only translates ACP
``session/update`` notifications into Pawrrtal :class:`StreamEvent`
records pushed onto an :class:`asyncio.Queue`, plus a tiny bit of
glue for filesystem + permission requests. The owning
:class:`.provider.GeminiCliLLM` drains the queue and yields the events
to the chat router.

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
from typing import Any, Literal

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
    EnvVariable,
    KillTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    SessionInfoUpdate,
    TerminalOutputResponse,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    UserMessageChunk,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

from app.agents.types import PermissionCheckFn
from app.providers.base import StreamEvent
from app.providers.gemini_cli.events import (
    _log_session_update,
    _stream_event_for_update,
)
from app.providers.gemini_cli.fs import (
    ensure_workspace_path,
    read_text_or_raise,
    slice_text,
    write_text_or_raise,
)

logger = logging.getLogger(__name__)


PermissionOptionKind = Literal["allow_once", "allow_always", "reject_once", "reject_always"]
"""The four ACP permission option kinds. Modelling as a ``Literal``
narrows :data:`ALLOW_KINDS` and surfaces typos in ``option.kind ==``
comparisons as type-checker errors rather than runtime falsities."""

ALLOW_KINDS: frozenset[PermissionOptionKind] = frozenset({"allow_once", "allow_always"})
"""Permission option kinds we treat as "approve" when auto-approving.
``allow_once`` is preferred over ``allow_always`` so an auto-approved
decision does not silently widen future permission scope."""

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
        display_by_name: dict[str, Any] | None = None,
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
            display_by_name: Optional display mapping for tools.
        """
        self._event_queue = event_queue
        self._workspace_root = workspace_root
        self._permission_check = permission_check
        self._display_by_name = display_by_name

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
        _log_session_update(session_id, update)
        event = _stream_event_for_update(update, self._display_by_name)
        if event is not None:
            await self._event_queue.put(event)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        """Approve or deny a tool-call permission request.

        When a Pawrrtal :data:`PermissionCheckFn` is bound, its decision
        wins; on denial we also push a ``StreamEvent(type="error")`` so
        the user sees *why* the chat stopped producing output instead of
        staring at a frozen partial response. When no closure is bound,
        we auto-approve via :func:`pick_allow_option`; when the spec
        offers no allow options we deny.
        """
        tool_name = tool_call.title or "<unknown>"
        logger.info(
            "GEMINI_CLI_PERMISSION_REQUEST session_id=%s tool_call_id=%s tool=%s options=%s",
            session_id,
            tool_call.tool_call_id,
            tool_name,
            [option.kind for option in options],
        )
        if self._permission_check is not None:
            arguments = tool_call.raw_input if isinstance(tool_call.raw_input, dict) else {}
            decision = await self._permission_check(tool_name, arguments)
            if not decision["allow"]:
                reason = decision["reason"] or "denied by Pawrrtal policy"
                logger.info(
                    "GEMINI_CLI_PERMISSION_DENIED tool=%s reason=%s",
                    tool_name,
                    reason,
                )
                await self._event_queue.put(
                    StreamEvent(
                        type="error",
                        content=f"Tool '{tool_name}' was denied: {reason}",
                    ),
                )
                return RequestPermissionResponse(outcome=DeniedOutcome(outcome=_DENY_OUTCOME))
        option = pick_allow_option(options)
        if option is None:
            logger.warning(
                "GEMINI_CLI_NO_ALLOW_OPTION tool=%s offered=%s",
                tool_name,
                [opt.kind for opt in options],
            )
            await self._event_queue.put(
                StreamEvent(
                    type="error",
                    content=(
                        f"Tool '{tool_name}' could not run: "
                        "no allow option was offered by the agent."
                    ),
                ),
            )
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome=_DENY_OUTCOME))
        logger.info(
            "GEMINI_CLI_PERMISSION_ALLOWED session_id=%s tool_call_id=%s tool=%s option_kind=%s",
            session_id,
            tool_call.tool_call_id,
            tool_name,
            option.kind,
        )
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
        resolved = ensure_workspace_path(path, self._workspace_root)
        text = read_text_or_raise(resolved, path)
        if line is not None or limit is not None:
            text = slice_text(text, line, limit)
        logger.info(
            "GEMINI_CLI_FS_READ session_id=%s path=%s resolved=%s chars=%d line=%s limit=%s",
            session_id,
            path,
            resolved,
            len(text),
            line,
            limit,
        )
        return ReadTextFileResponse(content=text)

    async def write_text_file(
        self,
        content: str,
        path: str,
        session_id: str,
        **kwargs: Any,
    ) -> WriteTextFileResponse | None:
        """Write a workspace-scoped file on the agent's behalf."""
        resolved = ensure_workspace_path(path, self._workspace_root)
        write_text_or_raise(resolved, content, path)
        logger.info(
            "GEMINI_CLI_FS_WRITE session_id=%s path=%s resolved=%s chars=%d",
            session_id,
            path,
            resolved,
            len(content),
        )
        return WriteTextFileResponse()

    # Terminal methods all raise ``method_not_found``; the ACP
    # ``initialize`` handshake declares ``terminal=False`` so a
    # well-behaved agent never calls them. Defence in depth in case
    # the agent ignores the capability list.

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
        """Terminals are not exposed; see class-level note."""
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        """Terminals are not exposed; see class-level note."""
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse | None:
        """Terminals are not exposed; see class-level note."""
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        """Terminals are not exposed; see class-level note."""
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalResponse | None:
        """Terminals are not exposed; see class-level note."""
        raise RequestError.method_not_found("terminal/kill")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Reject custom extension methods we did not opt into."""
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Ignore custom extension notifications we do not handle."""
        logger.debug("GEMINI_CLI_EXT_NOTIFICATION_IGNORED method=%s", method)

    def on_connect(self, conn: object) -> None:
        """Hook fired once the JSON-RPC connection is established."""
        logger.debug("GEMINI_CLI_ACP_CONNECTED")

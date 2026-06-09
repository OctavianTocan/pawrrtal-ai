# Antigravity agy CLI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Antigravity's local `agy` CLI as an experimental Pawrrtal provider that can use the user's local Antigravity / Google AI Ultra entitlement.

**Architecture:** Implement a black-box subprocess provider, similar in spirit to `GeminiCliLLM`, but without ACP. Each turn launches `agy --print`, passes absolute workspace roots via `--add-dir`, writes a per-turn log file, extracts the Antigravity conversation ID from logs, and resumes later turns with `--conversation`. The provider frames the prompt with a unique final-answer marker and emits the last marker block as Pawrrtal text, while tailing `--log-file` into structured provider logs.

**Tech Stack:** Python 3.12, FastAPI backend provider protocol, asyncio subprocesses, existing provider catalog/factory, pytest/anyio.

---

## Current Capability Assessment

`agy` can cover most basic provider behavior:

- Chat response: yes, via `agy --print`.
- Conversation continuation: yes, via `--conversation <id>` or `--continue`.
- Workspace access: yes, but only reliably when every workspace root is passed as an absolute `--add-dir`.
- Multiple workspace roots: yes.
- Concurrent requests: likely yes; tested concurrent subprocesses on distinct random localhost ports.
- Local subscription route: yes; logs showed keyring auth and `Gemini 3.5 Flash (High)`.
- Provider logs: partial; `--log-file` has auth/model/conversation/network lifecycle logs, but not full structured model/tool deltas.

Known gaps versus normal providers:

- Permission control is not yet equivalent. Current local settings have `toolPermission: "always-proceed"`, and `--sandbox --add-dir` still read and wrote outside `--add-dir` in probes.
- Tool events are not first-class. `agy` may perform file edits without log lines that identify the exact operation.
- Usage/cost accounting is unavailable from `--print` logs; emit `usage` with zeros or omit usage until a better signal is found.
- Images are not proven; treat `images` as unsupported and log ignored.
- Exit code is unreliable for timeout/cancel; timeouts and Ctrl-C returned exit code `0` with timeout text.

## Additional Tests Worth Running Before Shipping

- Explicit permission ask-mode probe: temporarily set Antigravity `toolPermission` to `ask`, run a tool-using `--print` call, confirm whether non-interactive mode blocks, auto-rejects, or has a CLI-side permission prompt channel. Restore settings immediately.
- Deny-mode probe if supported by settings: determine whether a global permission value can make provider mode read-only.
- Model selection probe: determine whether `agy` exposes a model flag or whether it only uses the user's selected Antigravity model.
- Large stdout probe: ask for a long response and confirm marker extraction is robust with multiple chunks and prior resumed output.
- Long tool-running cancellation probe in real app code: spawn via the provider wrapper, cancel the async generator, verify child process and local language server exit.
- Log tail rotation probe: confirm `--log-file` is created before the first auth/model lines and can be tailed while the process is live.
- Workspace boundary probe under a non-global temporary settings profile if a real app-data override is found.

## File Structure

- Create: `backend/app/providers/agy_cli/__init__.py`
  - Re-export provider and helper functions.
- Create: `backend/app/providers/agy_cli/command.py`
  - Build command argv, resolve binary, create log paths, hold constants.
- Create: `backend/app/providers/agy_cli/output.py`
  - Build framed prompts, extract the last final-answer marker, detect timeout/cancel stdout.
- Create: `backend/app/providers/agy_cli/session.py`
  - Parse Antigravity conversation IDs from logs.
- Create: `backend/app/providers/agy_cli/logs.py`
  - Tail `--log-file` and translate known lines into structured logs via `log_provider_stream_event`.
- Create: `backend/app/providers/agy_cli/provider.py`
  - Implement `AgyCliLLM` with subprocess lifecycle, continuation, error handling, and stream events.
- Create: `backend/app/providers/_catalog_agy_cli.py`
  - Catalog row for the local Antigravity CLI provider.
- Modify: `backend/app/providers/model_id.py`
  - Add `Host.agy_cli = "agy-cli"`.
- Modify: `backend/app/providers/catalog.py`
  - Include `AGY_CLI_ENTRIES`.
- Modify: `backend/app/providers/factory.py`
  - Route `Host.agy_cli` to `AgyCliLLM`.
- Modify: `backend/app/providers/__init__.py`
  - Export package if this file exposes provider symbols.
- Create: `backend/tests/test_agy_cli_provider.py`
  - Unit tests for command building, output framing, timeout detection, log parsing, factory/catalog routing, and subprocess stream behavior with a fake `agy` executable.
- Modify: `backend/tests/test_providers_and_schemas.py`
  - Add route assertion for `agy-cli:google/gemini-3.5-flash-high`.

## Task 1: Add Model ID and Catalog Wiring

**Files:**
- Modify: `backend/app/providers/model_id.py`
- Create: `backend/app/providers/_catalog_agy_cli.py`
- Modify: `backend/app/providers/catalog.py`
- Test: `backend/tests/test_agy_cli_provider.py`

- [ ] **Step 1: Write failing catalog tests**

Add to `backend/tests/test_agy_cli_provider.py`:

```python
"""Tests for the Antigravity agy CLI provider."""

from __future__ import annotations

from app.core.providers.catalog import MODEL_CATALOG
from app.core.providers.model_id import Host, Vendor, parse_model_id


def test_parse_model_id_accepts_agy_cli_host() -> None:
    parsed = parse_model_id("agy-cli:google/gemini-3.5-flash-high")

    assert parsed.host is Host.agy_cli
    assert parsed.vendor is Vendor.google
    assert parsed.model == "gemini-3.5-flash-high"
    assert parsed.id == "agy-cli:google/gemini-3.5-flash-high"


def test_catalog_lists_agy_cli_model() -> None:
    entries = [entry for entry in MODEL_CATALOG if entry.host is Host.agy_cli]

    assert [entry.model for entry in entries] == ["gemini-3.5-flash-high"]
    assert entries[0].vendor is Vendor.google
    assert entries[0].display_name == "Gemini 3.5 Flash High (Antigravity)"
    assert entries[0].cost_per_mtok_in_usd == 0.0
    assert entries[0].cost_per_mtok_out_usd == 0.0
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_parse_model_id_accepts_agy_cli_host tests/test_agy_cli_provider.py::test_catalog_lists_agy_cli_model -q
```

Expected: FAIL because `Host.agy_cli` and the catalog entry do not exist.

- [ ] **Step 3: Add host enum**

In `backend/app/providers/model_id.py`, add:

```python
class Host(StrEnum):
    """Where the model runs.

    One vendor's model can be served by many hosts (e.g. Claude via
    Agent SDK, Bedrock, Copilot).  ``litellm`` is the in-process
    LiteLLM SDK gateway — any vendor it can route to lives behind
    this single host enum.
    """

    agent_sdk = "agent-sdk"
    agy_cli = "agy-cli"
    gemini_cli = "gemini-cli"
    google_ai = "google-ai"
    litellm = "litellm"
    opencode_go = "opencode-go"
    xai = "xai"
```

- [ ] **Step 4: Add catalog rows**

Create `backend/app/providers/_catalog_agy_cli.py`:

```python
"""Antigravity agy CLI catalogue rows (``Host.agy_cli``)."""

from __future__ import annotations

from ._catalog_entries import ModelEntry
from .model_id import Host, Vendor

_AGY_CLI_IN_USD = 0.0
_AGY_CLI_OUT_USD = 0.0


AGY_CLI_ENTRIES: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.agy_cli,
        vendor=Vendor.google,
        model="gemini-3.5-flash-high",
        display_name="Gemini 3.5 Flash High (Antigravity)",
        short_name="Gemini 3.5 Flash High AGY",
        description="Local Antigravity CLI agent using the signed-in Google account",
        is_default=False,
        cost_per_mtok_in_usd=_AGY_CLI_IN_USD,
        cost_per_mtok_out_usd=_AGY_CLI_OUT_USD,
    ),
)
```

In `backend/app/providers/catalog.py`, import and include the new entries:

```python
from ._catalog_agy_cli import AGY_CLI_ENTRIES
```

```python
MODEL_CATALOG: tuple[ModelEntry, ...] = (
    *ANTHROPIC_ENTRIES,
    *GOOGLE_ENTRIES,
    *GEMINI_CLI_ENTRIES,
    *AGY_CLI_ENTRIES,
    *XAI_ENTRIES,
    *OPENAI_ENTRIES,
    *OPENCODE_GO_ENTRIES,
)
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_parse_model_id_accepts_agy_cli_host tests/test_agy_cli_provider.py::test_catalog_lists_agy_cli_model -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/model_id.py backend/app/providers/_catalog_agy_cli.py backend/app/providers/catalog.py backend/tests/test_agy_cli_provider.py
git commit -m "feat(providers): add Antigravity CLI catalog entry"
```

## Task 2: Add Command and Output Helpers

**Files:**
- Create: `backend/app/providers/agy_cli/__init__.py`
- Create: `backend/app/providers/agy_cli/command.py`
- Create: `backend/app/providers/agy_cli/output.py`
- Create: `backend/app/providers/agy_cli/session.py`
- Test: `backend/tests/test_agy_cli_provider.py`

- [ ] **Step 1: Add failing helper tests**

Append to `backend/tests/test_agy_cli_provider.py`:

```python
from pathlib import Path

from app.core.providers.agy_cli.command import AGY_BINARY_NAME, build_agy_command
from app.core.providers.agy_cli.output import (
    AGY_FINAL_CLOSE,
    AGY_FINAL_OPEN,
    build_framed_prompt,
    extract_final_answer,
    is_timeout_output,
)
from app.core.providers.agy_cli.session import parse_conversation_id


def test_build_agy_command_uses_absolute_workspace_and_log() -> None:
    command = build_agy_command(
        workspace_roots=[Path("/tmp/ws")],
        log_file=Path("/tmp/agy.log"),
        prompt="hello",
        timeout="10m",
        conversation_id="abc-123",
    )

    assert command == [
        AGY_BINARY_NAME,
        "--add-dir",
        "/tmp/ws",
        "--conversation",
        "abc-123",
        "--log-file",
        "/tmp/agy.log",
        "--print-timeout",
        "10m",
        "--print",
        "hello",
    ]


def test_extract_final_answer_returns_last_marker_block() -> None:
    stdout = (
        f"{AGY_FINAL_OPEN}old answer{AGY_FINAL_CLOSE}\n"
        "progress line\n"
        f"{AGY_FINAL_OPEN}new answer{AGY_FINAL_CLOSE}\n"
    )

    assert extract_final_answer(stdout) == "new answer"


def test_build_framed_prompt_wraps_history_and_question() -> None:
    prompt = build_framed_prompt(
        question="What next?",
        history=[{"role": "assistant", "content": "Prior answer"}],
        system_prompt="Be concise.",
    )

    assert "Be concise." in prompt
    assert "Assistant: Prior answer" in prompt
    assert "What next?" in prompt
    assert AGY_FINAL_OPEN in prompt
    assert AGY_FINAL_CLOSE in prompt


def test_timeout_output_detection_matches_agy_print_timeout() -> None:
    assert is_timeout_output("Error: timed out waiting for response\n") is True
    assert is_timeout_output("normal response") is False


def test_parse_conversation_id_prefers_created_then_resumed() -> None:
    created = "I server.go:747] Created conversation 1234-abcd\n"
    resumed = 'I printmode.go:125] Print mode: resuming conversation 9999-zzzz\n'

    assert parse_conversation_id(created) == "1234-abcd"
    assert parse_conversation_id(resumed) == "9999-zzzz"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py -q
```

Expected: FAIL because helper modules do not exist.

- [ ] **Step 3: Implement command helper**

Create `backend/app/providers/agy_cli/__init__.py`:

```python
"""Antigravity agy CLI provider package."""

from .provider import AgyCliLLM, is_agy_cli_available

__all__ = ["AgyCliLLM", "is_agy_cli_available"]
```

Create `backend/app/providers/agy_cli/command.py`:

```python
"""Command construction helpers for the Antigravity ``agy`` CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

AGY_BINARY_NAME = "agy"
DEFAULT_PRINT_TIMEOUT = "10m"


def is_agy_cli_available() -> bool:
    """Return whether the ``agy`` binary is resolvable on ``PATH``."""
    return shutil.which(AGY_BINARY_NAME) is not None


def build_agy_command(
    *,
    workspace_roots: list[Path],
    log_file: Path,
    prompt: str,
    timeout: str = DEFAULT_PRINT_TIMEOUT,
    conversation_id: str | None = None,
) -> list[str]:
    """Build the argv for one non-interactive ``agy --print`` turn."""
    command = [AGY_BINARY_NAME]
    for root in workspace_roots:
        command.extend(["--add-dir", str(root)])
    if conversation_id:
        command.extend(["--conversation", conversation_id])
    command.extend(
        [
            "--log-file",
            str(log_file),
            "--print-timeout",
            timeout,
            "--print",
            prompt,
        ]
    )
    return command
```

- [ ] **Step 4: Implement output helper**

Create `backend/app/providers/agy_cli/output.py`:

```python
"""Prompt framing and stdout parsing for ``agy --print``."""

from __future__ import annotations

import re

AGY_FINAL_OPEN = "<pawrrtal_final>"
AGY_FINAL_CLOSE = "</pawrrtal_final>"
_FINAL_RE = re.compile(
    re.escape(AGY_FINAL_OPEN) + r"(.*?)" + re.escape(AGY_FINAL_CLOSE),
    re.DOTALL,
)
_HISTORY_PREFIX_MAX_ROWS = 20
_HISTORY_PREFIX_MAX_CHARS = 12_000


def build_framed_prompt(
    *,
    question: str,
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> str:
    """Build a prompt that asks ``agy`` to wrap the final answer."""
    prefix = render_history_prefix(history, system_prompt)
    framing = (
        "Return your final user-visible answer inside exactly one "
        f"{AGY_FINAL_OPEN}...{AGY_FINAL_CLOSE} block. "
        "You may use tools before that, but do not put progress text inside the block.\n\n"
    )
    return framing + prefix + question


def extract_final_answer(stdout: str) -> str | None:
    """Return the last final-answer marker block from ``agy`` stdout."""
    matches = _FINAL_RE.findall(stdout)
    if not matches:
        return None
    return matches[-1].strip()


def is_timeout_output(stdout: str) -> bool:
    """Return whether stdout is the known ``agy --print`` timeout shape."""
    return "Error: timed out waiting for response" in stdout


def render_history_prefix(
    history: list[dict[str, str]] | None,
    system_prompt: str | None,
) -> str:
    """Render bounded system and prior-turn context for a fresh CLI turn."""
    sections: list[str] = []
    sp = (system_prompt or "").strip()
    if sp:
        sections.append(_wrap_section("SYSTEM CONTEXT", _truncate_tail(sp)))
    rendered_history = _render_history_lines(history)
    if rendered_history:
        sections.append(_wrap_section("PRIOR CONVERSATION", _truncate_tail(rendered_history)))
    return "\n".join(sections)


def _wrap_section(label: str, body: str) -> str:
    return f"--- BEGIN {label} ---\n{body}\n--- END {label} ---\n"


def _truncate_tail(text: str) -> str:
    if len(text) <= _HISTORY_PREFIX_MAX_CHARS:
        return text
    return "..." + text[-_HISTORY_PREFIX_MAX_CHARS:]


def _render_history_lines(history: list[dict[str, str]] | None) -> str:
    if not history:
        return ""
    rows = [
        row
        for row in history[-_HISTORY_PREFIX_MAX_ROWS:]
        if row.get("role") in {"user", "assistant"} and (row.get("content") or "").strip()
    ]
    lines: list[str] = []
    for row in rows:
        speaker = "User" if row["role"] == "user" else "Assistant"
        lines.append(f"{speaker}: {(row.get('content') or '').strip()}")
    return "\n".join(lines)
```

- [ ] **Step 5: Implement session parser**

Create `backend/app/providers/agy_cli/session.py`:

```python
"""Conversation ID parsing for Antigravity CLI logs."""

from __future__ import annotations

import re

_CREATED_RE = re.compile(r"Created conversation (?P<id>[a-zA-Z0-9-]+)")
_RESUMED_RE = re.compile(r"resuming conversation (?P<id>[a-zA-Z0-9-]+)")


def parse_conversation_id(log_text: str) -> str | None:
    """Extract the latest Antigravity conversation ID from a log body."""
    for pattern in (_CREATED_RE, _RESUMED_RE):
        match = pattern.search(log_text)
        if match is not None:
            return match.group("id")
    return None
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py -q
```

Expected: PASS for helper tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/providers/agy_cli backend/tests/test_agy_cli_provider.py
git commit -m "feat(providers): add agy CLI subprocess helpers"
```

## Task 3: Implement Provider Subprocess Flow

**Files:**
- Create: `backend/app/providers/agy_cli/provider.py`
- Modify: `backend/app/providers/agy_cli/__init__.py`
- Test: `backend/tests/test_agy_cli_provider.py`

- [ ] **Step 1: Add failing stream tests with fake subprocess**

Append:

```python
import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.core.providers.agy_cli.provider import AgyCliLLM


class FakeProcess:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode
        self.pid = 123

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode


@pytest.mark.anyio
async def test_agy_provider_yields_last_framed_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    log_file = tmp_path / "agy.log"

    async def fake_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
        log_file.write_text("I server.go:747] Created conversation conv-1\n")
        return FakeProcess(
            b"<pawrrtal_final>old</pawrrtal_final>\n<pawrrtal_final>new</pawrrtal_final>\n"
        )

    monkeypatch.setattr("app.core.providers.agy_cli.provider.is_agy_cli_available", lambda: True)
    monkeypatch.setattr("app.core.providers.agy_cli.provider._make_log_file", lambda _cid: log_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=tmp_path)
    events = [
        event
        async for event in provider.stream(
            "hello",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]

    assert events == [{"type": "delta", "content": "new"}]


@pytest.mark.anyio
async def test_agy_provider_surfaces_timeout_as_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    log_file = tmp_path / "agy.log"

    async def fake_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
        log_file.write_text("")
        return FakeProcess(b"Error: timed out waiting for response\n", returncode=0)

    monkeypatch.setattr("app.core.providers.agy_cli.provider.is_agy_cli_available", lambda: True)
    monkeypatch.setattr("app.core.providers.agy_cli.provider._make_log_file", lambda _cid: log_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=tmp_path)
    events = [
        event
        async for event in provider.stream(
            "hello",
            conversation_id=uuid4(),
            user_id=uuid4(),
        )
    ]

    assert events == [{"type": "error", "content": "Antigravity CLI timed out waiting for a response."}]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_agy_provider_yields_last_framed_answer tests/test_agy_cli_provider.py::test_agy_provider_surfaces_timeout_as_error -q
```

Expected: FAIL because `provider.py` is not implemented.

- [ ] **Step 3: Implement provider**

Create `backend/app/providers/agy_cli/provider.py`:

```python
"""Antigravity ``agy`` CLI provider.

This provider treats ``agy`` as a black-box local coding agent.  The CLI
does not expose ACP today, so we drive non-interactive print mode and
parse stdout/log files conservatively.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import NoReturn

import anyio

from app.core.agent_loop.types import AgentTool, PermissionCheckFn
from app.core.providers.base import ReasoningEffort, StreamEvent

from .command import DEFAULT_PRINT_TIMEOUT, build_agy_command, is_agy_cli_available
from .output import build_framed_prompt, extract_final_answer, is_timeout_output
from .session import parse_conversation_id

logger = logging.getLogger(__name__)


class AgyCliLLM:
    """``AILLM`` backed by local ``agy --print`` subprocess turns."""

    def __init__(self, model_id: str, *, workspace_root: Path | None = None) -> None:
        self._model_id = model_id
        self._workspace_root = workspace_root
        self._session_by_conversation: dict[uuid.UUID, str] = {}

    async def stream(
        self,
        question: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        history: list[dict[str, str]] | None = None,
        tools: list[AgentTool] | None = None,
        system_prompt: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        permission_check: PermissionCheckFn | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream one Antigravity CLI turn."""
        del user_id, permission_check
        if tools:
            logger.debug("AGY_CLI_TOOLS_IGNORED count=%d", len(tools))
        if reasoning_effort is not None:
            logger.debug("AGY_CLI_REASONING_EFFORT_IGNORED value=%s", reasoning_effort)
        if images:
            logger.debug("AGY_CLI_IMAGES_IGNORED count=%d", len(images))

        if not is_agy_cli_available():
            yield _error_event("Antigravity agy CLI binary not found on PATH.")
            return

        workspace_roots = await _workspace_roots(self._workspace_root)
        log_file = _make_log_file(conversation_id)
        prompt = build_framed_prompt(
            question=question,
            history=history,
            system_prompt=system_prompt,
        )
        command = build_agy_command(
            workspace_roots=workspace_roots,
            log_file=log_file,
            prompt=prompt,
            timeout=DEFAULT_PRINT_TIMEOUT,
            conversation_id=self._session_by_conversation.get(conversation_id),
        )
        proc = await _spawn(command, cwd=workspace_roots[0] if workspace_roots else None)
        if proc is None:
            yield _error_event("Failed to spawn Antigravity agy CLI subprocess.")
            return

        stdout = await _communicate(proc)
        self._remember_session(conversation_id, log_file)
        if is_timeout_output(stdout):
            yield _error_event("Antigravity CLI timed out waiting for a response.")
            return
        answer = extract_final_answer(stdout)
        if answer is None:
            logger.warning("AGY_CLI_FINAL_MARKER_MISSING stdout=%r", stdout[-500:])
            yield _error_event("Antigravity CLI returned an unframed response.")
            return
        yield StreamEvent(type="delta", content=answer)

    def _remember_session(self, conversation_id: uuid.UUID, log_file: Path) -> None:
        try:
            log_text = log_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("AGY_CLI_LOG_READ_FAILED path=%s reason=%s", log_file, exc)
            return
        agy_conversation_id = parse_conversation_id(log_text)
        if agy_conversation_id:
            self._session_by_conversation[conversation_id] = agy_conversation_id


async def _workspace_roots(workspace_root: Path | None) -> list[Path]:
    if workspace_root is None:
        return []
    return [Path(str(await anyio.Path(workspace_root).resolve()))]


def _make_log_file(conversation_id: uuid.UUID) -> Path:
    base = Path(tempfile.gettempdir()) / "pawrrtal-agy-cli"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{conversation_id}.log"


async def _spawn(
    command: list[str],
    *,
    cwd: Path | None,
) -> asyncio.subprocess.Process | None:
    try:
        return await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:
        logger.warning("AGY_CLI_SPAWN_FAILED reason=%s", exc)
        return None
    except OSError as exc:
        logger.warning("AGY_CLI_SPAWN_FAILED reason=%s", exc)
        return None


async def _communicate(proc: asyncio.subprocess.Process) -> str:
    stdout, stderr = await proc.communicate()
    if stderr:
        logger.debug("AGY_CLI_STDERR %s", stderr.decode(errors="replace")[-1000:])
    return stdout.decode(errors="replace")


def _error_event(message: str) -> StreamEvent:
    return StreamEvent(type="error", content=message)


def _missing_pipe(name: str) -> NoReturn:
    raise RuntimeError(f"Antigravity agy subprocess missing {name} pipe.")


__all__ = ["AgyCliLLM", "is_agy_cli_available"]
```

- [ ] **Step 4: Run stream tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_agy_provider_yields_last_framed_answer tests/test_agy_cli_provider.py::test_agy_provider_surfaces_timeout_as_error -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/agy_cli/provider.py backend/app/providers/agy_cli/__init__.py backend/tests/test_agy_cli_provider.py
git commit -m "feat(providers): stream Antigravity CLI subprocess turns"
```

## Task 4: Wire Factory Routing

**Files:**
- Modify: `backend/app/providers/factory.py`
- Modify: `backend/tests/test_agy_cli_provider.py`
- Modify: `backend/tests/test_providers_and_schemas.py`

- [ ] **Step 1: Add failing factory tests**

Append:

```python
from app.core.providers.agy_cli import AgyCliLLM
from app.core.providers.factory import resolve_llm


def test_factory_routes_agy_cli_host_to_agy_cli_llm() -> None:
    provider = resolve_llm("agy-cli:google/gemini-3.5-flash-high")

    assert isinstance(provider, AgyCliLLM)
    assert provider._model_id == "gemini-3.5-flash-high"
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_factory_routes_agy_cli_host_to_agy_cli_llm -q
```

Expected: FAIL because `HOST_TO_PROVIDER` lacks `Host.agy_cli`.

- [ ] **Step 3: Wire factory**

In `backend/app/providers/factory.py`, import and route:

```python
from .agy_cli import AgyCliLLM
```

```python
HOST_TO_PROVIDER: dict[Host, type[AILLM]] = {
    Host.agent_sdk: ClaudeLLM,
    Host.agy_cli: AgyCliLLM,
    Host.gemini_cli: GeminiCliLLM,
    Host.google_ai: GeminiLLM,
    Host.litellm: LiteLLMLLM,
    Host.opencode_go: OpencodeGoLLM,
    Host.xai: XaiLLM,
}
```

```python
if provider_cls is AgyCliLLM:
    return AgyCliLLM(parsed.model, workspace_root=workspace_root)
```

- [ ] **Step 4: Run factory tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_factory_routes_agy_cli_host_to_agy_cli_llm tests/test_gemini_cli_provider.py::test_factory_host_table_is_exhaustive -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/factory.py backend/tests/test_agy_cli_provider.py backend/tests/test_providers_and_schemas.py
git commit -m "feat(providers): route agy CLI model IDs"
```

## Task 5: Add Structured Log Tailing

**Files:**
- Create: `backend/app/providers/agy_cli/logs.py`
- Modify: `backend/app/providers/agy_cli/provider.py`
- Test: `backend/tests/test_agy_cli_provider.py`

- [ ] **Step 1: Add failing log parser tests**

Append:

```python
from app.core.providers.agy_cli.logs import classify_log_line


def test_classify_log_line_model_selection() -> None:
    event = classify_log_line(
        'I model_config_manager.go:157] Propagating selected model override to backend: label="Gemini 3.5 Flash (High)"'
    )

    assert event == {
        "event": "model_selected",
        "summary": "Gemini 3.5 Flash (High)",
    }


def test_classify_log_line_tool_confirmation() -> None:
    event = classify_log_line(
        'I tool_confirmation_manager.go:72] Auto-approving tool confirmation: "Edit" at step 6'
    )

    assert event == {
        "event": "tool_permission_auto_approved",
        "summary": "Edit",
    }
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py::test_classify_log_line_model_selection tests/test_agy_cli_provider.py::test_classify_log_line_tool_confirmation -q
```

Expected: FAIL because `logs.py` does not exist.

- [ ] **Step 3: Implement log classifier**

Create `backend/app/providers/agy_cli/logs.py`:

```python
"""Structured logging helpers for Antigravity CLI log files."""

from __future__ import annotations

import re
from typing import TypedDict


class AgyLogEvent(TypedDict):
    event: str
    summary: str


_MODEL_RE = re.compile(r'label="(?P<label>[^"]+)"')
_TOOL_CONFIRM_RE = re.compile(r'Auto-approving tool confirmation: "(?P<tool>[^"]+)"')
_CREATED_RE = re.compile(r"Created conversation (?P<id>[a-zA-Z0-9-]+)")
_RESUMED_RE = re.compile(r"resuming conversation (?P<id>[a-zA-Z0-9-]+)")


def classify_log_line(line: str) -> AgyLogEvent | None:
    """Classify a known ``agy`` log line into a stable structured event."""
    if "Propagating selected model override" in line:
        match = _MODEL_RE.search(line)
        return {"event": "model_selected", "summary": match.group("label") if match else "unknown"}
    if "Auto-approving tool confirmation" in line:
        match = _TOOL_CONFIRM_RE.search(line)
        return {
            "event": "tool_permission_auto_approved",
            "summary": match.group("tool") if match else "unknown",
        }
    created = _CREATED_RE.search(line)
    if created:
        return {"event": "conversation_created", "summary": created.group("id")}
    resumed = _RESUMED_RE.search(line)
    if resumed:
        return {"event": "conversation_resumed", "summary": resumed.group("id")}
    if "timed out" in line:
        return {"event": "timeout", "summary": "print mode timed out"}
    return None
```

- [ ] **Step 4: Add provider log integration**

In `backend/app/providers/agy_cli/provider.py`, after `stdout = await _communicate(proc)`, read log lines and emit structured logs:

```python
from app.core.providers._stream_logging import log_provider_stream_event

from .logs import classify_log_line
```

```python
        _log_agy_events(log_file, conversation_id, self._model_id)
```

Add:

```python
def _log_agy_events(log_file: Path, conversation_id: uuid.UUID, model_id: str) -> None:
    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("AGY_CLI_LOG_READ_FAILED path=%s reason=%s", log_file, exc)
        return
    for line in lines:
        event = classify_log_line(line)
        if event is None:
            continue
        log_provider_stream_event(
            logger,
            provider="agy-cli",
            event_type=event["event"],
            model=model_id,
            conversation_id=conversation_id,
            summary=event["summary"],
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/agy_cli/logs.py backend/app/providers/agy_cli/provider.py backend/tests/test_agy_cli_provider.py
git commit -m "feat(providers): log Antigravity CLI activity"
```

## Task 6: Harden Cancellation, Return Codes, and Missing Markers

**Files:**
- Modify: `backend/app/providers/agy_cli/provider.py`
- Modify: `backend/app/providers/agy_cli/output.py`
- Test: `backend/tests/test_agy_cli_provider.py`

- [ ] **Step 1: Add tests for non-zero exit and unframed stdout**

Append:

```python
@pytest.mark.anyio
async def test_agy_provider_surfaces_unframed_stdout_as_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    log_file = tmp_path / "agy.log"

    async def fake_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
        log_file.write_text("")
        return FakeProcess(b"plain answer\n", returncode=0)

    monkeypatch.setattr("app.core.providers.agy_cli.provider.is_agy_cli_available", lambda: True)
    monkeypatch.setattr("app.core.providers.agy_cli.provider._make_log_file", lambda _cid: log_file)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)

    provider = AgyCliLLM("gemini-3.5-flash-high", workspace_root=tmp_path)
    events = [event async for event in provider.stream("hello", uuid4(), uuid4())]

    assert events == [{"type": "error", "content": "Antigravity CLI returned an unframed response."}]
```

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py -q
```

Expected: PASS after Task 3 behavior.

- [ ] **Step 3: Add explicit cancellation handling**

Wrap `_communicate(proc)` in `try/except asyncio.CancelledError`:

```python
        try:
            stdout = await _communicate(proc)
        except asyncio.CancelledError:
            await _shutdown_process(proc)
            logger.info("AGY_CLI_CANCELLED conversation_id=%s model=%s", conversation_id, self._model_id)
            raise
```

Add:

```python
async def _shutdown_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return
    except TimeoutError:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        return
    await proc.wait()
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/agy_cli/provider.py backend/app/providers/agy_cli/output.py backend/tests/test_agy_cli_provider.py
git commit -m "fix(providers): harden agy CLI subprocess failures"
```

## Task 7: Document Experimental Permission Semantics

**Files:**
- Modify: `backend/app/providers/agy_cli/provider.py`
- Create: `docs/superpowers/plans/2026-05-21-antigravity-agy-cli-provider.md` if not already committed
- Optional Modify: `frontend/content/docs/handbook/decisions/2026-05-21-add-antigravity-cli-provider.md`

- [ ] **Step 1: Add provider docstring warning**

Update `backend/app/providers/agy_cli/provider.py` module docstring:

```python
"""Antigravity ``agy`` CLI provider.

This provider treats ``agy`` as a black-box local coding agent.  The CLI
does not expose ACP today, so we drive non-interactive print mode and
parse stdout/log files conservatively.

Security note: ``agy`` permission behavior is governed by the user's
global Antigravity CLI settings. In local probes, ``--sandbox`` did not
enforce a strict ``--add-dir`` workspace boundary when
``toolPermission`` was ``always-proceed``. Do not present this provider
as Pawrrtal-enforced tool approval until ask-mode has been tested and
integrated.
"""
```

- [ ] **Step 2: Add runtime warning when permission_check is supplied**

In `AgyCliLLM.stream`, replace `del user_id, permission_check` with:

```python
        del user_id
        if permission_check is not None:
            logger.warning(
                "AGY_CLI_PERMISSION_CHECK_UNSUPPORTED conversation_id=%s model=%s",
                conversation_id,
                self._model_id,
            )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/providers/agy_cli/provider.py docs/superpowers/plans/2026-05-21-antigravity-agy-cli-provider.md
git commit -m "docs(providers): document agy CLI permission limits"
```

## Task 8: Final Verification

**Files:**
- All files touched above.

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd backend && uv run pytest tests/test_agy_cli_provider.py tests/test_providers_and_schemas.py tests/test_gemini_cli_provider.py -q
```

Expected: PASS.

- [ ] **Step 2: Run provider lint**

Run:

```bash
cd backend && uv run ruff check app/providers/agy_cli app/providers/_catalog_agy_cli.py app/providers/factory.py app/providers/model_id.py tests/test_agy_cli_provider.py
```

Expected: PASS.

- [ ] **Step 3: Run repo check if time allows**

Run:

```bash
just check
```

Expected: PASS.

- [ ] **Step 4: Manual smoke test with local `agy`**

Run against a disposable workspace:

```bash
mkdir -p /private/tmp/pawrrtal-agy-smoke
printf 'alpha\nbeta\n' > /private/tmp/pawrrtal-agy-smoke/notes.txt
cd backend
uv run pytest tests/test_agy_cli_provider.py -q
```

Then run one real chat through the app UI with `agy-cli:google/gemini-3.5-flash-high` selected and verify:

- The first response appears in the chat.
- A follow-up turn remembers prior context.
- Backend logs contain `provider=agy-cli` lifecycle events.
- A timeout is displayed as an error instead of an empty assistant message.

- [ ] **Step 5: Commit final fixes**

```bash
git add backend/app/providers backend/tests docs/superpowers/plans/2026-05-21-antigravity-agy-cli-provider.md
git commit -m "feat(providers): add experimental Antigravity CLI provider"
```

## Self-Review

Spec coverage:

- Provider catalog/factory routing: Tasks 1 and 4.
- One-shot chat: Task 3.
- Continuation: Task 3 stores parsed conversation IDs; follow-up uses `--conversation`.
- Workspace access: Task 2 command helper requires absolute `--add-dir`.
- Logs: Task 5.
- Timeout/cancel: Task 6.
- Permission caveat: Task 7.
- Verification: Task 8.

Placeholder scan:

- No `TBD`, `TODO`, or "implement later" placeholders remain.
- Known unknowns are listed as explicit additional tests, not hidden implementation steps.

Type consistency:

- Provider class is consistently `AgyCliLLM`.
- Host enum is consistently `Host.agy_cli` with wire value `agy-cli`.
- Catalog model is consistently `gemini-3.5-flash-high`.

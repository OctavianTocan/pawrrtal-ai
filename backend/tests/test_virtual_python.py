"""Tests for the in-process ``python`` agent tool.

Unit tests cover the executor's functional contract:
  - stdout / stderr capture, error formatting
  - workspace-rooted ``fs`` helper (read, write, ls, glob, jail)
  - wall-clock timeout
  - output-cap truncation (and its precedence over the timeout)
  - process-state isolation between calls (sys.path, os.environ)
  - concurrent calls serialise via the asyncio lock

One integration test exercises the agent-loop dispatch path via the
shared ``ScriptedStreamFn`` harness so a future refactor of the tool
factory can't silently break tool-call wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.types import AgentTool
from app.tools.errors import ToolErrorCode
from app.tools.python_exec import make_virtual_python_tool
from tests.agent_harness import (
    ScriptedStreamFn,
    run_scenario,
    text_turn,
    tool_call_turn,
)

# Shared defaults for the tracer-bullet tests.  Kept small so the test
# suite stays fast and the timeout path is exercisable with a real
# sleep without a long wall-clock.
_TEST_TIMEOUT_SECONDS = 5.0
_TEST_OUTPUT_CAP_BYTES = 4_000


def _make_tool(
    workspace: Path, *, timeout: float | None = None, cap: int | None = None
) -> AgentTool:
    return make_virtual_python_tool(
        workspace_root=workspace,
        timeout_seconds=timeout if timeout is not None else _TEST_TIMEOUT_SECONDS,
        output_cap_bytes=cap if cap is not None else _TEST_OUTPUT_CAP_BYTES,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Seed a workspace with a couple of files the tool can poke at."""
    (tmp_path / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "note.md").write_text("hello world", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Output capture
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_print_is_captured(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c1", code="print('hi')")
    assert out == "hi\n"


@pytest.mark.anyio
async def test_multiline_runs_in_order(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c2", code="x = 1\nprint(x + 1)\nprint('done')")
    assert out == "2\ndone\n"


@pytest.mark.anyio
async def test_stdout_and_stderr_interleave(workspace: Path) -> None:
    tool = _make_tool(workspace)
    code = "import sys\nprint('A')\nsys.stderr.write('B\\n')\nprint('C')\n"
    out = await tool.execute("c3", code=code)
    # All three lines land in the combined buffer in source order.
    assert "A" in out
    assert "B" in out
    assert "C" in out


@pytest.mark.anyio
async def test_uncaught_exception_returns_traceback(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c4", code="1 / 0")
    assert "Traceback" in out
    assert "ZeroDivisionError" in out


@pytest.mark.anyio
async def test_assertion_failure_surfaces_message(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c5", code="assert False, 'nope'")
    assert "AssertionError" in out
    assert "nope" in out


@pytest.mark.anyio
async def test_empty_code_returns_invalid_path_error(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c6", code="   ")
    assert out.startswith(f"[{ToolErrorCode.INVALID_PATH.value}]")


# ---------------------------------------------------------------------------
# Workspace filesystem helper
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fs_read_round_trips_existing_file(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c7", code="print(fs.read('memory/note.md'))")
    assert out.strip() == "hello world"


@pytest.mark.anyio
async def test_fs_write_persists_to_workspace(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute(
        "c8",
        code="fs.write('out.txt', 'agent wrote me')\nprint('ok')",
    )
    assert "ok" in out
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "agent wrote me"


@pytest.mark.anyio
async def test_fs_ls_returns_sorted_entries_with_dir_suffix(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c9", code="print(fs.ls(''))")
    # Dirs sort first (memory/) then files (AGENTS.md).
    assert "memory/" in out
    assert "AGENTS.md" in out


@pytest.mark.anyio
async def test_fs_glob_finds_workspace_files(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c10", code="print(fs.glob('**/*.md'))")
    assert "AGENTS.md" in out
    assert "memory/note.md" in out


@pytest.mark.anyio
async def test_fs_read_missing_file_raises_in_user_code(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c11", code="print(fs.read('nope.md'))")
    # The exception propagates out of user code and lands in the
    # combined buffer as a traceback — model can react to it.
    assert "FileNotFoundError" in out


@pytest.mark.anyio
async def test_fs_read_outside_workspace_raises_permission_error(workspace: Path) -> None:
    tool = _make_tool(workspace)
    out = await tool.execute("c12", code="print(fs.read('../escape.md'))")
    assert "PermissionError" in out
    assert ToolErrorCode.OUT_OF_ROOT.value in out


@pytest.mark.anyio
async def test_fs_write_refuses_to_follow_symlinks(tmp_path: Path) -> None:
    """A symlink at the write path must surface ``PermissionError`` and
    leave the symlink target untouched.  Closes the same TOCTOU window
    ``write_file`` does, but for the ``fs`` helper exposed inside the
    ``python`` tool — without it, agent code calling ``os.symlink``
    earlier in the same turn could overwrite an arbitrary file via a
    subsequent ``fs.write`` call.
    """
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target_outside = outside / "secret.txt"
    target_outside.write_text("original", encoding="utf-8")
    (root / "peek.txt").symlink_to(target_outside)

    tool = make_virtual_python_tool(
        workspace_root=root,
        timeout_seconds=_TEST_TIMEOUT_SECONDS,
        output_cap_bytes=_TEST_OUTPUT_CAP_BYTES,
    )
    out = await tool.execute(
        "c-write-symlink",
        code="fs.write('peek.txt', 'OVERWRITTEN')",
    )
    assert "PermissionError" in out
    assert target_outside.read_text(encoding="utf-8") == "original"


@pytest.mark.anyio
async def test_fs_glob_excludes_symlinks(tmp_path: Path) -> None:
    """``fs.glob`` filters symlinks so the model never sees paths it
    can't safely read or write (``O_NOFOLLOW`` would reject them
    later).
    """
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "real.txt").write_text("hi", encoding="utf-8")
    (root / "link.txt").symlink_to(root / "real.txt")

    tool = make_virtual_python_tool(
        workspace_root=root,
        timeout_seconds=_TEST_TIMEOUT_SECONDS,
        output_cap_bytes=_TEST_OUTPUT_CAP_BYTES,
    )
    out = await tool.execute(
        "c-glob-symlink",
        code="print(sorted(fs.glob('*.txt')))",
    )
    assert "real.txt" in out
    assert "link.txt" not in out


# ---------------------------------------------------------------------------
# Timeout and output cap
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_timeout_fires_on_slow_code(workspace: Path) -> None:
    tool = _make_tool(workspace, timeout=0.3)
    out = await tool.execute("c13", code="import time; time.sleep(2)")
    assert out.startswith("[timeout]")


@pytest.mark.anyio
async def test_output_cap_truncates_with_head_and_tail(workspace: Path) -> None:
    tool = _make_tool(workspace, cap=200)
    code = "print('A' * 500)\nprint('END-MARKER')"
    out = await tool.execute("c14", code=code)
    # Both ends survive the head+tail truncation; the marker line lives
    # at the tail so the agent can see "what was the last thing printed".
    assert "truncated" in out
    assert "END-MARKER" in out
    assert "A" in out


@pytest.mark.anyio
async def test_output_cap_wins_over_timeout(workspace: Path) -> None:
    # Tight cap, generous timeout — a tight-loop print should hit the
    # cap and return immediately, well before the timeout.
    tool = _make_tool(workspace, cap=200, timeout=10.0)
    code = "for _ in range(10_000): print('x' * 100)"
    out = await tool.execute("c15", code=code)
    assert "truncated" in out
    # Crucial assertion: we did NOT time out.
    assert not out.startswith("[timeout]")


# ---------------------------------------------------------------------------
# State isolation between calls
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sys_path_mutation_does_not_leak(workspace: Path) -> None:
    tool = _make_tool(workspace)
    await tool.execute("c16a", code="import sys; sys.path.append('/tmp/leak-xyz')")
    out = await tool.execute(
        "c16b",
        code="import sys; print('/tmp/leak-xyz' in sys.path)",
    )
    assert "False" in out


@pytest.mark.anyio
async def test_os_environ_mutation_does_not_leak(workspace: Path) -> None:
    tool = _make_tool(workspace)
    await tool.execute("c17a", code="import os; os.environ['LEAK_XYZ'] = '1'")
    out = await tool.execute(
        "c17b",
        code="import os; print(os.environ.get('LEAK_XYZ'))",
    )
    assert "None" in out


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_concurrent_calls_serialise_without_deadlock(workspace: Path) -> None:
    import asyncio

    tool = _make_tool(workspace)
    a, b = await asyncio.gather(
        tool.execute("c18a", code="print('first')"),
        tool.execute("c18b", code="print('second')"),
    )
    assert a == "first\n"
    assert b == "second\n"


# ---------------------------------------------------------------------------
# Integration: tool dispatches correctly through the agent loop
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tool_dispatches_through_agent_loop(workspace: Path) -> None:
    tool = _make_tool(workspace)
    script = ScriptedStreamFn(
        [
            tool_call_turn("python", {"code": "print(2 + 2)"}),
            text_turn("4"),
        ]
    )
    events = await run_scenario(script, tools=[tool])
    assert script.call_count == 2
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_results) == 1
    assert "4" in tool_results[0]["content"]
    assert tool_results[0]["is_error"] is False


# ---------------------------------------------------------------------------
# Display payload — closes #302
# ---------------------------------------------------------------------------


def test_display_present_surfaces_first_line_of_code(workspace: Path) -> None:
    """``present`` shows the first non-blank line, not just ``(code)``."""
    tool = _make_tool(workspace)
    assert tool.display is not None
    payload = tool.display.render({"code": "import os\nprint(os.environ.get('HOME'))"})
    assert "import os" in payload["present"]
    # The argument key alone (``(code)``) was the old behaviour — must not
    # be the only thing surfaced.
    assert payload["present"] != "🛠 Running Python (code)"


def test_display_present_handles_empty_code(workspace: Path) -> None:
    tool = _make_tool(workspace)
    assert tool.display is not None
    payload = tool.display.render({"code": ""})
    assert "(empty)" in payload["present"]


def test_display_present_truncates_long_first_line(workspace: Path) -> None:
    tool = _make_tool(workspace)
    assert tool.display is not None
    long_line = "x = " + "1+" * 200 + "1"
    payload = tool.display.render({"code": long_line})
    # Truncation marker must appear; raw value must not leak full length.
    assert "…" in payload["present"]
    assert len(payload["present"]) < len(long_line) + 100


def test_display_detail_renders_fenced_block(workspace: Path) -> None:
    tool = _make_tool(workspace)
    assert tool.display is not None
    payload = tool.display.render({"code": "print('hi')"})
    assert payload.get("detail", "").startswith("```python")
    assert "print('hi')" in payload["detail"]


def test_display_detail_truncates_oversized_code(workspace: Path) -> None:
    tool = _make_tool(workspace)
    assert tool.display is not None
    huge = "# " + "x" * 5000
    payload = tool.display.render({"code": huge})
    detail = payload.get("detail", "")
    assert "…" in detail
    assert len(detail) < len(huge) + 100

"""Tests for workspace-scoped agent file tools.

Covers:
  - Path-traversal protection (out-of-root attempts return ToolError).
  - Read / write / list happy paths.
  - Error code surface (NOT_FOUND, WRONG_KIND, BINARY_FILE, OUT_OF_ROOT).
  - Stable error rendering (`[code] message` shape) so the chat surface
    and the upcoming permissions gate can match on `code` directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.tools.errors import ToolError, ToolErrorCode
from app.core.tools.workspace_files import make_workspace_tools


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Seed a small workspace tree the tools can poke at."""
    (tmp_path / "AGENTS.md").write_text("# Agent rules\n", encoding="utf-8")
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "note.md").write_text("hello", encoding="utf-8")
    return tmp_path


def _tools(root: Path) -> dict[str, object]:
    """Return the workspace tools keyed by name for ergonomic access."""
    return {tool.name: tool for tool in make_workspace_tools(root)}


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_file_returns_text_for_existing_file(workspace: Path) -> None:
    read = _tools(workspace)["read_file"]
    out = await read.execute("call-1", path="AGENTS.md")  # type: ignore[attr-defined]
    assert "Agent rules" in out


@pytest.mark.anyio
async def test_read_file_rejects_path_outside_workspace(workspace: Path) -> None:
    read = _tools(workspace)["read_file"]
    out = await read.execute("call-2", path="../../etc/passwd")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.OUT_OF_ROOT.value}]")


@pytest.mark.anyio
async def test_read_file_reports_not_found(workspace: Path) -> None:
    read = _tools(workspace)["read_file"]
    out = await read.execute("call-3", path="missing.md")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.NOT_FOUND.value}]")


@pytest.mark.anyio
async def test_read_file_rejects_directory_target(workspace: Path) -> None:
    read = _tools(workspace)["read_file"]
    out = await read.execute("call-4", path="memory")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.WRONG_KIND.value}]")


@pytest.mark.anyio
async def test_read_file_reports_binary_file(workspace: Path) -> None:
    (workspace / "blob.bin").write_bytes(b"\x00\x01\x02\xff")
    read = _tools(workspace)["read_file"]
    out = await read.execute("call-5", path="blob.bin")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.BINARY_FILE.value}]")


@pytest.mark.anyio
async def test_read_file_requires_path_argument(workspace: Path) -> None:
    read = _tools(workspace)["read_file"]
    out = await read.execute("call-6")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.INVALID_PATH.value}]")


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_write_file_creates_new_file(workspace: Path) -> None:
    write = _tools(workspace)["write_file"]
    out = await write.execute(  # type: ignore[attr-defined]
        "call-7", path="memory/2026-05-08.md", content="day log"
    )
    assert "Written" in out
    assert (workspace / "memory" / "2026-05-08.md").read_text() == "day log"


@pytest.mark.anyio
async def test_write_file_creates_parent_dirs(workspace: Path) -> None:
    write = _tools(workspace)["write_file"]
    out = await write.execute(  # type: ignore[attr-defined]
        "call-8", path="skills/new/SKILL.md", content="---\nname: x\n---\n"
    )
    assert "Written" in out
    assert (workspace / "skills" / "new" / "SKILL.md").exists()


@pytest.mark.anyio
async def test_write_file_blocks_traversal(workspace: Path) -> None:
    write = _tools(workspace)["write_file"]
    out = await write.execute(  # type: ignore[attr-defined]
        "call-9", path="../escape.md", content="evil"
    )
    assert out.startswith(f"[{ToolErrorCode.OUT_OF_ROOT.value}]")
    assert not (workspace.parent / "escape.md").exists()


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_dir_lists_root_when_no_path(workspace: Path) -> None:
    listd = _tools(workspace)["list_dir"]
    out = await listd.execute("call-10")  # type: ignore[attr-defined]
    assert "AGENTS.md" in out
    assert "memory/" in out


@pytest.mark.anyio
async def test_list_dir_rejects_file_target(workspace: Path) -> None:
    listd = _tools(workspace)["list_dir"]
    out = await listd.execute("call-11", path="AGENTS.md")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.WRONG_KIND.value}]")


@pytest.mark.anyio
async def test_list_dir_reports_not_found(workspace: Path) -> None:
    listd = _tools(workspace)["list_dir"]
    out = await listd.execute("call-12", path="nope")  # type: ignore[attr-defined]
    assert out.startswith(f"[{ToolErrorCode.NOT_FOUND.value}]")


# ---------------------------------------------------------------------------
# ToolError rendering
# ---------------------------------------------------------------------------


def test_tool_error_render_uses_stable_prefix() -> None:
    err = ToolError(ToolErrorCode.PERMISSION_DENIED, "denied by mode")
    rendered = err.render()
    assert rendered.startswith(f"[{ToolErrorCode.PERMISSION_DENIED.value}]")
    assert "denied by mode" in rendered


# ---------------------------------------------------------------------------
# Resolver hardening (sibling-prefix + symlink-on-read)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_file_rejects_sibling_directory_prefix(tmp_path: Path) -> None:
    """A sibling whose name shares a string prefix with the workspace
    root must NOT be reachable via path traversal — string-prefix
    comparison (the previous behaviour) accepted ``abc-evil`` when the
    root was ``abc``.
    """
    root = tmp_path / "abc"
    root.mkdir()
    sibling = tmp_path / "abc-evil"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("leak", encoding="utf-8")
    (root / "AGENTS.md").write_text("ok", encoding="utf-8")

    read = _tools(root)["read_file"]
    out = await read.execute(  # type: ignore[attr-defined]
        "sibling-1", path="../abc-evil/secret.txt"
    )
    assert out.startswith(f"[{ToolErrorCode.OUT_OF_ROOT.value}]")


@pytest.mark.anyio
async def test_read_file_refuses_to_follow_symlinks(tmp_path: Path) -> None:
    """A symlink placed *inside* the workspace pointing outside must
    not exfiltrate the target.  ``O_NOFOLLOW`` at open time closes the
    TOCTOU window between ``resolve()`` and the actual read.
    """
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "AGENTS.md").write_text("ok", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("leak", encoding="utf-8")
    link = root / "peek.txt"
    link.symlink_to(secret)

    read = _tools(root)["read_file"]
    out = await read.execute("symlink-1", path="peek.txt")  # type: ignore[attr-defined]
    # The resolver containment check rejects it (resolved path is outside
    # the workspace).  This test pins the behaviour so a regression that
    # only fixes the prefix check but re-enables symlink-following gets
    # caught.
    assert out.startswith(f"[{ToolErrorCode.OUT_OF_ROOT.value}]")


@pytest.mark.anyio
async def test_write_file_refuses_to_follow_symlinks(tmp_path: Path) -> None:
    """``write_file`` must not overwrite a file outside the workspace
    via a symlink planted inside the workspace.  Closes the write-side
    of the TOCTOU window that the read-side ``O_NOFOLLOW`` already
    covered.
    """
    root = tmp_path / "workspace"
    root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    target_outside = outside / "secret.txt"
    target_outside.write_text("original", encoding="utf-8")
    link = root / "peek.txt"
    link.symlink_to(target_outside)

    write = _tools(root)["write_file"]
    out = await write.execute(  # type: ignore[attr-defined]
        "symlink-write-1", path="peek.txt", content="OVERWRITTEN"
    )
    assert out.startswith(f"[{ToolErrorCode.OUT_OF_ROOT.value}]")
    # And the outside target was NOT modified.
    assert target_outside.read_text(encoding="utf-8") == "original"

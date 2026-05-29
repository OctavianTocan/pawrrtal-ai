"""Tests for ``app.governance.bash_boundary``.

Port-of-port — exercises every CCT scenario plus the bash separators
our agent loop sees in practice (``&&``, ``||``, ``;``, ``|``, ``&``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.governance.bash_boundary import check_bash_directory_boundary


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Use the pytest ``tmp_path`` fixture as the approved + working dir."""
    return tmp_path


class TestReadOnlyCommandsAllowed:
    """Read-only commands skip per-argument boundary checks."""

    @pytest.mark.parametrize(
        "command",
        ["ls", "ls -la", "ls /etc", "cat /etc/passwd", "echo hello"],
    )
    def test_allowed(self, command: str, workspace: Path) -> None:
        allowed, _ = check_bash_directory_boundary(command, workspace, workspace)
        assert allowed is True


class TestFsModifyingInsideWorkspace:
    """FS-modifying commands targeting paths inside the workspace are allowed."""

    def test_rm_relative_inside_workspace(self, workspace: Path) -> None:
        (workspace / "garbage.txt").write_text("x")
        allowed, _ = check_bash_directory_boundary("rm garbage.txt", workspace, workspace)
        assert allowed is True

    def test_mkdir_subdir(self, workspace: Path) -> None:
        allowed, _ = check_bash_directory_boundary("mkdir new_dir", workspace, workspace)
        assert allowed is True

    def test_cp_relative(self, workspace: Path) -> None:
        (workspace / "src").write_text("x")
        allowed, _ = check_bash_directory_boundary("cp src dst", workspace, workspace)
        assert allowed is True


class TestFsModifyingOutsideWorkspace:
    """FS-modifying commands escaping the workspace root are denied."""

    def test_rm_absolute_outside(self, workspace: Path) -> None:
        allowed, reason = check_bash_directory_boundary("rm /etc/passwd", workspace, workspace)
        assert allowed is False
        assert reason is not None
        assert "/etc/passwd" in reason
        assert "Directory boundary violation" in reason

    def test_rm_relative_traversal(self, workspace: Path) -> None:
        allowed, reason = check_bash_directory_boundary("rm ../../private", workspace, workspace)
        assert allowed is False
        assert reason is not None

    def test_cp_destination_outside(self, workspace: Path) -> None:
        allowed, reason = check_bash_directory_boundary("cp safe /etc/breach", workspace, workspace)
        assert allowed is False
        assert reason is not None
        assert "/etc/breach" in reason


class TestCommandChains:
    """Bash separators split commands; any denied component fails the chain."""

    @pytest.mark.parametrize("separator", ["&&", "||", ";", "|", "&"])
    def test_chain_with_one_bad_command(self, workspace: Path, separator: str) -> None:
        command = f"ls {separator} rm /etc/passwd"
        allowed, reason = check_bash_directory_boundary(command, workspace, workspace)
        assert allowed is False
        assert reason is not None

    def test_chain_all_safe(self, workspace: Path) -> None:
        (workspace / "a").write_text("x")
        (workspace / "b").write_text("x")
        allowed, _ = check_bash_directory_boundary("ls && rm a && rm b", workspace, workspace)
        assert allowed is True


class TestFindMutators:
    """``find`` is read-only unless ``-delete`` / ``-exec`` is present."""

    def test_find_read_only(self, workspace: Path) -> None:
        allowed, _ = check_bash_directory_boundary("find . -name '*.txt'", workspace, workspace)
        assert allowed is True

    def test_find_delete_inside_workspace(self, workspace: Path) -> None:
        (workspace / "old.txt").write_text("x")
        allowed, _ = check_bash_directory_boundary(
            "find . -name '*.txt' -delete", workspace, workspace
        )
        # No specific path argument outside workspace → allowed.
        assert allowed is True

    def test_find_delete_at_root(self, workspace: Path) -> None:
        allowed, reason = check_bash_directory_boundary("find / -delete", workspace, workspace)
        assert allowed is False
        assert reason is not None
        assert "find" in reason


class TestUnparseableCommand:
    """When ``shlex`` chokes, we fall through to the OS-level sandbox."""

    def test_mismatched_quotes_passes_through(self, workspace: Path) -> None:
        allowed, reason = check_bash_directory_boundary("rm 'unbalanced", workspace, workspace)
        # Unparseable → True (defer to OS).
        assert allowed is True
        assert reason is None

"""Tests for ``app.governance.permissions``.

Each individual check covers one denial dimension; the composed
default bundle is exercised end-to-end to confirm short-circuit
ordering (most specific failure surfaces first).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.governance.permissions import (
    PermissionContext,
    PermissionDecision,
    build_default_permission_check,
    check_bash_command_boundary,
    check_file_path_boundary,
    check_workspace_allowlist,
    compose_permission_checks,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def context(tmp_path: Path) -> PermissionContext:
    """Default PermissionContext used by most cases — no allowlist."""
    return PermissionContext(
        user_id=str(uuid.uuid4()),
        workspace_root=tmp_path,
        conversation_id=str(uuid.uuid4()),
        surface="web",
    )


class TestWorkspaceAllowlist:
    async def test_none_allowlist_permits_anything(self, context: PermissionContext) -> None:
        decision = await check_workspace_allowlist("Bash", {}, context)
        assert decision.allow is True

    async def test_member_of_allowlist(self, tmp_path: Path) -> None:
        ctx = PermissionContext(
            user_id="u",
            workspace_root=tmp_path,
            conversation_id="c",
            surface="web",
            enabled_tools=frozenset({"workspace_read"}),
        )
        decision = await check_workspace_allowlist("workspace_read", {}, ctx)
        assert decision.allow is True

    async def test_non_member_denied(self, tmp_path: Path) -> None:
        ctx = PermissionContext(
            user_id="u",
            workspace_root=tmp_path,
            conversation_id="c",
            surface="web",
            enabled_tools=frozenset({"workspace_read"}),
        )
        decision = await check_workspace_allowlist("Bash", {}, ctx)
        assert decision.allow is False
        assert decision.violation_type == "tool_disabled_by_workspace"


class TestFilePathBoundary:
    async def test_inside_workspace(self, context: PermissionContext) -> None:
        decision = await check_file_path_boundary("workspace_read", {"path": "notes.md"}, context)
        assert decision.allow is True

    async def test_traversal_denied(self, context: PermissionContext) -> None:
        decision = await check_file_path_boundary(
            "workspace_read", {"path": "../../etc/passwd"}, context
        )
        assert decision.allow is False
        assert decision.violation_type == "path_outside_workspace"

    async def test_absolute_outside(self, context: PermissionContext) -> None:
        decision = await check_file_path_boundary("Write", {"file_path": "/etc/passwd"}, context)
        assert decision.allow is False
        assert decision.violation_type == "path_outside_workspace"

    async def test_forbidden_filename_in_workspace(self, context: PermissionContext) -> None:
        decision = await check_file_path_boundary("workspace_read", {"path": ".env"}, context)
        assert decision.allow is False
        assert decision.violation_type == "forbidden_filename"

    async def test_dangerous_pattern_pem(self, context: PermissionContext) -> None:
        decision = await check_file_path_boundary(
            "workspace_read", {"path": "certs/private.pem"}, context
        )
        assert decision.allow is False
        assert decision.violation_type == "forbidden_filename"

    async def test_non_file_tool_passes_through(self, context: PermissionContext) -> None:
        decision = await check_file_path_boundary("exa_search", {"query": "anything"}, context)
        assert decision.allow is True


class TestBashCommandBoundary:
    async def test_safe_command(self, context: PermissionContext) -> None:
        decision = await check_bash_command_boundary("Bash", {"command": "ls -la"}, context)
        assert decision.allow is True

    async def test_escape_denied(self, context: PermissionContext) -> None:
        decision = await check_bash_command_boundary("Bash", {"command": "rm /etc/passwd"}, context)
        assert decision.allow is False
        assert decision.violation_type == "bash_directory_boundary"

    async def test_non_bash_tool_passes_through(self, context: PermissionContext) -> None:
        decision = await check_bash_command_boundary("workspace_read", {"path": "x"}, context)
        assert decision.allow is True


class TestCompose:
    async def test_default_bundle_denies_bash_escape(self, context: PermissionContext) -> None:
        check = build_default_permission_check()
        decision = await check("Bash", {"command": "rm /etc/passwd"}, context)
        assert decision.allow is False
        assert decision.violation_type == "bash_directory_boundary"

    async def test_default_bundle_denies_forbidden_filename(
        self, context: PermissionContext
    ) -> None:
        check = build_default_permission_check()
        decision = await check("workspace_read", {"path": "id_rsa"}, context)
        assert decision.allow is False
        assert decision.violation_type == "forbidden_filename"

    async def test_default_bundle_allows_normal_call(self, context: PermissionContext) -> None:
        check = build_default_permission_check()
        decision = await check("exa_search", {"query": "rust async"}, context)
        assert decision.allow is True

    async def test_compose_short_circuits_on_first_denial(self, context: PermissionContext) -> None:
        async def deny_always(
            _a: str, _b: dict[str, Any], _c: PermissionContext
        ) -> PermissionDecision:
            return PermissionDecision.deny(reason="nope", violation_type="test")

        # If short-circuit works, the second check (which would crash) never runs.
        async def crash_always(
            _a: str, _b: dict[str, Any], _c: PermissionContext
        ) -> PermissionDecision:
            raise RuntimeError("should not be called")

        check = compose_permission_checks(deny_always, crash_always)
        decision = await check("anything", {}, context)
        assert decision.allow is False
        assert decision.reason == "nope"

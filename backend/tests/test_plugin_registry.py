"""Tests for the plugin registry and its interaction with build_agent_tools.

These tests exercise the additive seam: a plugin registered through
:func:`register_plugin` must contribute tools through
:func:`build_agent_tools` only when (a) the call supplies both
``user_id`` and ``workspace_id`` and (b) the plugin's activation
predicate returns ``True``.

Core tool composition is verified by the existing ``test_agent_tools``
suite; here we only assert that plugins extend that list correctly
and don't perturb the core tools' order.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.agent_loop.types import AgentTool
from app.core.agent_tools import build_agent_tools
from app.core.plugins import (
    EnvKeySpec,
    Plugin,
    ToolContext,
    all_plugins,
    register_plugin,
)
from app.core.plugins.registry import reset_for_tests


@pytest.fixture(autouse=True)
def _reset_registry() -> Generator[None]:
    """Empty the registry before and after each test to avoid cross-test bleed."""
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Minimal workspace directory the core tools accept."""
    (tmp_path / "AGENTS.md").write_text("# Test workspace")
    return tmp_path


def _make_tool(name: str) -> AgentTool:
    """Return a trivial AgentTool used to detect plugin contribution."""

    async def _execute(_tool_call_id: str, **_kwargs: object) -> str:
        return f"ok:{name}"

    return AgentTool(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        execute=_execute,
    )


def _factory(name: str):
    def _build(_ctx: ToolContext) -> AgentTool:
        return _make_tool(name)

    return _build


class TestRegistration:
    def test_registers_plugin(self) -> None:
        plugin = Plugin(id="alpha", name="Alpha", description="x")
        register_plugin(plugin)

        assert [p.id for p in all_plugins()] == ["alpha"]

    def test_duplicate_id_rejected(self) -> None:
        register_plugin(Plugin(id="alpha", name="A", description="x"))

        with pytest.raises(ValueError, match="already registered"):
            register_plugin(Plugin(id="alpha", name="A again", description="y"))

    def test_preserves_registration_order(self) -> None:
        for pid in ("a", "b", "c"):
            register_plugin(Plugin(id=pid, name=pid, description=""))

        assert [p.id for p in all_plugins()] == ["a", "b", "c"]


class TestPluginsContributeToolsToAgent:
    def test_registered_factory_appends_tool(self, tmp_workspace: Path) -> None:
        register_plugin(
            Plugin(
                id="alpha",
                name="Alpha",
                description="",
                tool_factories=(_factory("alpha_tool"),),
            )
        )

        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(
                workspace_root=tmp_workspace,
                user_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
            )

        assert "alpha_tool" in [t.name for t in tools]

    def test_plugin_tools_appended_after_core(self, tmp_workspace: Path) -> None:
        """Plugin tools land at the end of the list — stable order matters
        for the Claude bridge's allowed_tools whitelist."""
        register_plugin(
            Plugin(
                id="alpha",
                name="Alpha",
                description="",
                tool_factories=(_factory("alpha_tool"),),
            )
        )

        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(
                workspace_root=tmp_workspace,
                user_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
            )

        assert tools[-1].name == "alpha_tool"


class TestActivationGating:
    def test_skipped_when_required_env_key_missing(self, tmp_workspace: Path) -> None:
        register_plugin(
            Plugin(
                id="needy",
                name="Needy",
                description="",
                env_keys=(EnvKeySpec(name="NEEDY_API_KEY", label="Needy"),),
                tool_factories=(_factory("needy_tool"),),
            )
        )

        # resolve_api_key returns None → required key missing → plugin skipped.
        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(
                workspace_root=tmp_workspace,
                user_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
            )

        assert "needy_tool" not in [t.name for t in tools]

    def test_included_when_required_env_key_present(self, tmp_workspace: Path) -> None:
        register_plugin(
            Plugin(
                id="needy",
                name="Needy",
                description="",
                env_keys=(EnvKeySpec(name="NEEDY_API_KEY", label="Needy"),),
                tool_factories=(_factory("needy_tool"),),
            )
        )

        # Match the NEEDY_API_KEY lookup specifically; return None for
        # everything else so core capability-gated tools (Exa,
        # image-gen) stay absent and the assertion is unambiguous.
        # We patch BOTH binding sites because Python's `from X import Y`
        # captures a local reference; the activation predicate looks up
        # the registry copy while core gating reads the keys-module copy.
        def _resolve(_user_id, key_name: str) -> str | None:
            return "secret-value" if key_name == "NEEDY_API_KEY" else None

        with (
            patch("app.core.keys.resolve_api_key", side_effect=_resolve),
            patch("app.core.plugins.registry.resolve_api_key", side_effect=_resolve),
        ):
            tools = build_agent_tools(
                workspace_root=tmp_workspace,
                user_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
            )

        assert "needy_tool" in [t.name for t in tools]

    def test_custom_predicate_overrides_default(self, tmp_workspace: Path) -> None:
        register_plugin(
            Plugin(
                id="picky",
                name="Picky",
                description="",
                env_keys=(EnvKeySpec(name="PICKY_KEY", label="Picky"),),
                tool_factories=(_factory("picky_tool"),),
                # Custom predicate ignores env keys and always activates.
                is_activated=lambda _ctx: True,
            )
        )

        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(
                workspace_root=tmp_workspace,
                user_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
            )

        assert "picky_tool" in [t.name for t in tools]


class TestLegacyCallersUnaffected:
    """Existing callers that don't yet thread workspace_id keep working."""

    def test_no_plugin_tools_when_workspace_id_missing(self, tmp_workspace: Path) -> None:
        register_plugin(
            Plugin(
                id="alpha",
                name="Alpha",
                description="",
                tool_factories=(_factory("alpha_tool"),),
            )
        )

        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace)

        assert "alpha_tool" not in [t.name for t in tools]

    def test_no_plugin_tools_when_user_id_missing(self, tmp_workspace: Path) -> None:
        register_plugin(
            Plugin(
                id="alpha",
                name="Alpha",
                description="",
                tool_factories=(_factory("alpha_tool"),),
            )
        )

        with patch("app.core.keys.resolve_api_key", return_value=None):
            tools = build_agent_tools(workspace_root=tmp_workspace, workspace_id=uuid.uuid4())

        assert "alpha_tool" not in [t.name for t in tools]

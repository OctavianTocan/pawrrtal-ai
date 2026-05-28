"""Tests for ``paw verify all`` dispatcher.

Asserts include/exclude filter behaviour, JSON aggregation shape, and
the exit-6-if-any-suite-fails contract. Suite runners are stubbed at the
import surface so this test file stays focused on the dispatcher logic.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app
from app.cli.paw.verify.scenarios import ScenarioResult

MOCK_BACKEND = "http://test-backend"


def _seed_persona(profile: str = "default") -> PersonaState:
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
        default_workspace_id="ws-1",
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


def _passing(name: str) -> ScenarioResult:
    r = ScenarioResult(name=name)
    r.add(f"{name}_dummy_ok", True)
    return r


def _failing(name: str) -> ScenarioResult:
    r = ScenarioResult(name=name)
    r.add(f"{name}_dummy_fail", False, detail="injected")
    return r


def _stub_all_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every suite runner with a passing stub."""

    async def _ok(name: str) -> ScenarioResult:
        return _passing(name)

    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_codex_scenario",
        lambda *a, **kw: _ok("codex"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_chat_roundtrip_scenario",
        lambda *a, **kw: _ok("chat-roundtrip"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_model_switch_scenario",
        lambda *a, **kw: _ok("model-switch"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_telegram_scenario",
        lambda *a, **kw: _ok("telegram"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_cost_scenario",
        lambda *a, **kw: _ok("cost"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_lcm_scenario",
        lambda *a, **kw: _ok("lcm"),
    )


def _stub_one_failing(monkeypatch: pytest.MonkeyPatch, failing_suite: str) -> None:
    """Stub all runners; mark ``failing_suite`` as a failing result."""

    async def _ok(name: str) -> ScenarioResult:
        return _passing(name)

    async def _bad(name: str) -> ScenarioResult:
        return _failing(name)

    def _runner_for(name: str) -> Callable[..., Awaitable[ScenarioResult]]:
        if name == failing_suite:
            return lambda *a, **kw: _bad(name)
        return lambda *a, **kw: _ok(name)

    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_codex_scenario",
        _runner_for("codex"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_chat_roundtrip_scenario",
        _runner_for("chat-roundtrip"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_model_switch_scenario",
        _runner_for("model-switch"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_telegram_scenario",
        _runner_for("telegram"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_cost_scenario",
        _runner_for("cost"),
    )
    monkeypatch.setattr(
        "app.cli.paw.commands.verify.run_lcm_scenario",
        _runner_for("lcm"),
    )


def _patch_paw_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``PawClient`` so the dispatcher doesn't touch HTTP at all."""

    class _NoopClient:
        async def __aenter__(self) -> _NoopClient:
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

    def _factory(*_args: Any, **_kwargs: Any) -> _NoopClient:
        return _NoopClient()

    monkeypatch.setattr("app.cli.paw.commands.verify.PawClient", _factory)


def test_verify_all_runs_default_suites_and_returns_aggregated_json(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``paw verify all --json`` returns the canonical-order list of suite results."""
    _patch_paw_client(monkeypatch)
    _stub_all_passing(monkeypatch)
    result = runner.invoke(app, ["verify", "all", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert [r["scenario"] for r in payload] == [
        "codex",
        "chat-roundtrip",
        "model-switch",
        "telegram",
        "cost",
        "lcm",
    ]
    assert all(r["passed"] is True for r in payload)


def test_verify_all_exit_6_when_any_suite_fails(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failing suite flips exit code to 6 even though others passed."""
    _patch_paw_client(monkeypatch)
    _stub_one_failing(monkeypatch, "chat-roundtrip")
    result = runner.invoke(app, ["verify", "all", "--json"])

    assert result.exit_code == 6, result.stdout
    payload = json.loads(result.stdout)
    passed_by_name = {r["scenario"]: r["passed"] for r in payload}
    assert passed_by_name == {
        "codex": True,
        "chat-roundtrip": False,
        "model-switch": True,
        "telegram": True,
        "cost": True,
        "lcm": True,
    }


def test_include_filters_to_named_suites(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--include`` runs only the named suites in canonical order."""
    _patch_paw_client(monkeypatch)
    _stub_all_passing(monkeypatch)
    result = runner.invoke(
        app,
        ["verify", "all", "--include", "chat-roundtrip,model-switch", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert [r["scenario"] for r in payload] == ["chat-roundtrip", "model-switch"]


def test_exclude_drops_named_suites(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--exclude`` drops the named suites and keeps the rest in order."""
    _patch_paw_client(monkeypatch)
    _stub_all_passing(monkeypatch)
    result = runner.invoke(app, ["verify", "all", "--exclude", "codex", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert [r["scenario"] for r in payload] == [
        "chat-roundtrip",
        "model-switch",
        "telegram",
        "cost",
        "lcm",
    ]


def test_unknown_include_is_local_error(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typo in ``--include`` exits with the LocalError code, not silently."""
    _patch_paw_client(monkeypatch)
    _stub_all_passing(monkeypatch)
    result = runner.invoke(app, ["verify", "all", "--include", "noexist", "--json"])

    assert result.exit_code == 1, result.stdout


def test_include_and_exclude_compose(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--include`` then ``--exclude`` narrow to the intersection."""
    _patch_paw_client(monkeypatch)
    _stub_all_passing(monkeypatch)
    result = runner.invoke(
        app,
        [
            "verify",
            "all",
            "--include",
            "codex,chat-roundtrip",
            "--exclude",
            "codex",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert [r["scenario"] for r in payload] == ["chat-roundtrip"]


def test_all_filtered_out_is_local_error(
    runner: CliRunner,
    seeded: PersonaState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Excluding every suite reports a LocalError instead of returning empty."""
    _patch_paw_client(monkeypatch)
    _stub_all_passing(monkeypatch)
    result = runner.invoke(
        app,
        [
            "verify",
            "all",
            "--exclude",
            "codex,chat-roundtrip,model-switch,telegram,cost,lcm",
            "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout

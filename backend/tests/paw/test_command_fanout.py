"""Tests for ``paw fanout`` — local orchestrator over N parallel personas.

Children are never actually spawned: ``asyncio.create_subprocess_exec`` is
monkeypatched to return a deterministic fake process so the suite stays
fast and doesn't require a running backend.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.cli.paw import config as paw_config
from app.cli.paw.commands import fanout as fanout_module
from app.cli.paw.main import app


class _FakeProc:
    """Minimal stand-in for ``asyncio.subprocess.Process`` used by fanout."""

    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


@pytest.fixture
def captured_spawns(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every fake subprocess invocation for assertions.

    Defaults to ``exit=0`` with empty stdout/stderr. Tests that need
    custom child outputs (e.g. failing child) install their own
    ``asyncio.create_subprocess_exec`` monkeypatch directly.
    """
    calls: list[dict[str, Any]] = []

    async def fake_create(
        *args: str,
        env: dict[str, str] | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
    ) -> _FakeProc:
        calls.append({"args": list(args), "env": dict(env or {})})
        return _FakeProc(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    return calls


@pytest.fixture
def serialized_spawns(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Like ``captured_spawns`` but records slot ordering for concurrency tests.

    Each fake child yields once via ``asyncio.sleep(0)`` so sibling tasks
    get a chance to interleave; the ``max`` field of the returned dict
    records the peak number of children active at the same time.
    """
    order: list[int] = []
    active = {"count": 0, "max": 0}
    counter = {"i": 0}

    async def fake_create(*args: str, env: dict[str, str] | None = None, **_: Any) -> _FakeProc:
        slot = counter["i"]
        counter["i"] += 1
        order.append(slot)
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await asyncio.sleep(0)
        active["count"] -= 1
        return _FakeProc(returncode=0, stdout=f"slot{slot}\n".encode(), stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    return {"order": order, "active": active}


def test_fanout_spawns_n_children_with_distinct_paw_profile_env(runner, captured_spawns):
    """3 slots -> 3 subprocess calls, each with a unique PAW_PROFILE."""
    result = runner.invoke(app, ["fanout", "3", "auth", "status", "--json"])
    assert result.exit_code == 0, result.stdout
    assert len(captured_spawns) == 3
    profiles = sorted(call["env"]["PAW_PROFILE"] for call in captured_spawns)
    assert profiles == ["paw-fanout-0", "paw-fanout-1", "paw-fanout-2"]
    # Each child also gets a distinct isolated config directory.
    config_dirs = {call["env"]["PAW_CONFIG_DIR"] for call in captured_spawns}
    assert len(config_dirs) == 3


def test_fanout_passes_wrapped_args_to_each_child(runner, captured_spawns):
    """Every wrapped arg appears verbatim in every child's argv."""
    runner.invoke(
        app,
        ["fanout", "2", "conversations", "send", "hello", "--new"],
    )
    assert len(captured_spawns) == 2
    for call in captured_spawns:
        # argv = [python, -m, app.cli.paw.main, ...wrapped]
        assert call["args"][-4:] == ["conversations", "send", "hello", "--new"]
        assert call["args"][1] == "-m"
        assert call["args"][2] == "app.cli.paw.main"


def test_fanout_aggregate_exit_is_max_of_children(runner, monkeypatch):
    """A single child exit=5 bubbles to parent exit=5."""

    async def fake_create(*args, env=None, **_):
        # Slot index is read from PAW_PROFILE; slot 1 fails with 5.
        profile = env["PAW_PROFILE"] if env else ""
        rc = 5 if profile.endswith("-1") else 0
        return _FakeProc(returncode=rc, stdout=b"", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    result = runner.invoke(app, ["fanout", "3", "auth", "status"])
    assert result.exit_code == 5


def test_fanout_max_concurrent_one_serialises(runner, serialized_spawns):
    """--max-concurrent 1 means at most one child active at any moment."""
    result = runner.invoke(
        app,
        ["fanout", "4", "--max-concurrent", "1", "auth", "status"],
    )
    assert result.exit_code == 0, result.stdout
    assert serialized_spawns["order"] == [0, 1, 2, 3]
    assert serialized_spawns["active"]["max"] == 1


def test_fanout_json_output_schema(runner, monkeypatch):
    """--json emits a list of {slot, profile, exit_code, stdout, stderr, duration_ms}."""

    async def fake_create(*args, env=None, **_):
        slot = int(env["PAW_PROFILE"].rsplit("-", 1)[1])
        return _FakeProc(
            returncode=0,
            stdout=f"hello-{slot}\n".encode(),
            stderr=b"",
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    result = runner.invoke(app, ["fanout", "2", "--json", "auth", "status"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert isinstance(payload, list)
    assert len(payload) == 2
    expected_keys = {"slot", "profile", "exit_code", "stdout", "stderr", "duration_ms"}
    for row in payload:
        assert set(row.keys()) == expected_keys
        assert isinstance(row["slot"], int)
        assert isinstance(row["duration_ms"], int)
    assert {row["slot"] for row in payload} == {0, 1}


def test_fanout_default_cleanup_removes_slot_dirs(runner, captured_spawns, tmp_path):
    """Without --keep-personas, each per-slot config dir is gone after the run."""
    runner.invoke(app, ["fanout", "2", "auth", "status"])
    # Slot dirs are created under config_root(); the conftest pins
    # PAW_CONFIG_DIR to tmp_path, so check there for stragglers.
    root = paw_config.config_root()
    survivors = [p for p in root.glob(".fanout-paw-fanout-*") if p.is_dir()]
    assert survivors == []


def test_fanout_keep_personas_skips_cleanup(runner, captured_spawns):
    """--keep-personas leaves the per-slot config dirs in place for inspection."""
    runner.invoke(app, ["fanout", "2", "--keep-personas", "auth", "status"])
    root = paw_config.config_root()
    survivors = sorted(p.name for p in root.glob(".fanout-paw-fanout-*") if p.is_dir())
    assert survivors == [".fanout-paw-fanout-0", ".fanout-paw-fanout-1"]


def test_fanout_custom_persona_prefix(runner, captured_spawns):
    """--persona-prefix changes the slot names without affecting count."""
    runner.invoke(
        app,
        ["fanout", "2", "--persona-prefix", "stress", "auth", "status"],
    )
    profiles = sorted(call["env"]["PAW_PROFILE"] for call in captured_spawns)
    assert profiles == ["stress-0", "stress-1"]


def test_fanout_requires_wrapped_command(runner):
    """Bare `paw fanout 3` with no wrapped command is a LocalError (exit 1)."""
    result = runner.invoke(app, ["fanout", "3"])
    assert result.exit_code == 1


def test_fanout_rejects_zero_slots(runner):
    """`paw fanout 0 ...` is a usage error."""
    result = runner.invoke(app, ["fanout", "0", "auth", "status"])
    assert result.exit_code == 1


def test_fanout_rejects_slots_above_safety_cap(runner):
    """Asking for >MAX_SLOTS is rejected to avoid a fork-bomb."""
    over = fanout_module.MAX_SLOTS + 1
    result = runner.invoke(app, ["fanout", str(over), "auth", "status"])
    assert result.exit_code == 1


def test_fanout_help_text_renders(runner):
    """`paw fanout --help` exits 0 and includes an example."""
    result = runner.invoke(app, ["fanout", "--help"])
    assert result.exit_code == 0
    assert "fanout" in result.stdout.lower()


def test_fanout_child_env_inherits_paw_config_dir_unique_per_slot(
    runner, captured_spawns, tmp_path
):
    """Each child's PAW_CONFIG_DIR lives under the parent's config root."""
    runner.invoke(app, ["fanout", "3", "auth", "status"])
    root = Path(paw_config.config_root())
    for call in captured_spawns:
        child_dir = Path(call["env"]["PAW_CONFIG_DIR"])
        assert child_dir.parent == root
        assert child_dir.name.startswith(".fanout-paw-fanout-")


def test_fanout_strips_paw_record_from_child_env(runner, captured_spawns, monkeypatch):
    """``PAW_RECORD`` in the parent env must not leak into spawned children.

    Otherwise N slots overwrite each other's rows in the same recorder
    file and the parent's recorded fixture is corrupted with interleaved
    request rows from every child. Children that need to record should
    be invoked under their own ``paw record`` wrapper.
    """
    monkeypatch.setenv("PAW_RECORD", "/tmp/paw-record-parent.jsonl")
    result = runner.invoke(app, ["fanout", "2", "auth", "status"])
    assert result.exit_code == 0, result.stdout
    assert len(captured_spawns) == 2
    for call in captured_spawns:
        assert "PAW_RECORD" not in call["env"], (
            "child inherited PAW_RECORD; would corrupt the parent fixture"
        )


def test_fanout_plain_output_emits_tsv_rows(runner, monkeypatch):
    """--plain emits one TSV row per slot: slot, exit_code, duration_ms, stdout_size."""

    async def fake_create(*args, env=None, **_):
        slot = int(env["PAW_PROFILE"].rsplit("-", 1)[1])
        return _FakeProc(
            returncode=0,
            stdout=f"hello-{slot}\n".encode(),
            stderr=b"",
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    result = runner.invoke(app, ["fanout", "2", "--plain", "auth", "status"])
    assert result.exit_code == 0, result.stdout
    rows = [
        line.split("\t") for line in result.stdout.strip().splitlines() if line and "\t" in line
    ]
    assert len(rows) == 2
    for row in rows:
        assert len(row) == 4  # slot, exit_code, duration_ms, stdout_size_bytes
        int(row[0])
        int(row[1])
        int(row[2])
        int(row[3])


def test_fanout_rejects_json_plus_plain(runner):
    """--json and --plain are mutually exclusive (fail with exit=1)."""
    result = runner.invoke(
        app,
        ["fanout", "2", "--json", "--plain", "auth", "status"],
    )
    assert result.exit_code == 1


def test_fanout_preserves_provider_secrets_for_same_backend_children(
    runner, captured_spawns, monkeypatch
):
    """Provider credentials reach every fanout child.

    Fanout children hit the same backend the parent is configured for —
    they need the same provider keys to drive turns through the LLM. The
    env-allowlist must therefore explicitly forward ``ANTHROPIC_API_KEY``
    / ``OPENAI_API_KEY`` / etc.

    Unrelated tokens (``GH_TOKEN``, ``AUTH_SECRET``) must NOT flow even
    when the backend is local — they're not on the allowlist and the
    children don't need them.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-secret")
    monkeypatch.setenv("GH_TOKEN", "should-not-leak")
    monkeypatch.setenv("AUTH_SECRET", "should-not-leak")
    result = runner.invoke(app, ["fanout", "2", "auth", "status"])
    assert result.exit_code == 0, result.stdout
    assert len(captured_spawns) == 2
    for call in captured_spawns:
        assert call["env"].get("ANTHROPIC_API_KEY") == "anthropic-secret"
        assert call["env"].get("OPENAI_API_KEY") == "openai-secret"
        assert call["env"].get("XAI_API_KEY") == "xai-secret"
        assert call["env"].get("GOOGLE_API_KEY") == "google-secret"
        # Off-allowlist secrets must not flow into children.
        assert "GH_TOKEN" not in call["env"]
        assert "AUTH_SECRET" not in call["env"]


def test_fanout_terminates_child_on_per_slot_timeout(runner, monkeypatch):
    """``--per-slot-timeout`` reaps a hung child via terminate()→kill().

    Uses a fake process that never returns from ``communicate()``; the
    test hangs without the ``asyncio.wait_for`` guard. Counts
    ``terminate()`` calls to verify the cleanup path runs.
    """
    terminate_calls: list[int] = []

    class _HangingProc:
        returncode: int | None = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(60)
            return b"", b""

        def terminate(self) -> None:
            terminate_calls.append(id(self))
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode if self.returncode is not None else 0

    async def fake_create(*args, env=None, **_):
        return _HangingProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    result = runner.invoke(
        app,
        ["fanout", "2", "--per-slot-timeout", "1", "auth", "status"],
    )
    # Both slots time out → aggregate exit non-zero.
    assert result.exit_code != 0, result.stdout
    assert len(terminate_calls) == 2, terminate_calls

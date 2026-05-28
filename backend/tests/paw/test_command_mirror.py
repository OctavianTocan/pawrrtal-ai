"""Tests for ``paw mirror`` — local vs remote SSE diff.

Children are never actually spawned: ``asyncio.create_subprocess_exec``
is monkeypatched to return a deterministic fake process per side so the
suite stays fast and doesn't require a running backend.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.cli.paw import config as paw_config
from app.cli.paw.commands import mirror as mirror_module
from app.cli.paw.main import app


class _FakeProc:
    """Minimal stand-in for ``asyncio.subprocess.Process`` used by mirror."""

    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _make_send_payload(
    *,
    final_text: str,
    events: dict[str, int],
    conversation_id: str = "11111111-1111-1111-1111-111111111111",
) -> bytes:
    """Build a stdout payload shaped like ``paw conversations send --json``."""
    body = {
        "conversation_id": conversation_id,
        "model_id": "litellm:openai/gpt-4o-mini",
        "codex_thread_id": None,
        "final_text": final_text,
        "events": events,
        "duration_ms": 100,
    }
    return (json.dumps(body) + "\n").encode("utf-8")


def _install_fake_spawns(
    monkeypatch: pytest.MonkeyPatch,
    by_backend_url: dict[str, _FakeProc],
) -> list[dict[str, Any]]:
    """Install a fake ``create_subprocess_exec`` that dispatches by ``PAW_BACKEND_URL``.

    Returns a list that records each spawn's argv + env for assertions.
    """
    calls: list[dict[str, Any]] = []

    async def fake_create(
        *args: str,
        env: dict[str, str] | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
    ) -> _FakeProc:
        env_dict = dict(env or {})
        calls.append({"args": list(args), "env": env_dict})
        backend_url = env_dict.get("PAW_BACKEND_URL", "")
        if backend_url not in by_backend_url:
            raise AssertionError(
                f"Unexpected PAW_BACKEND_URL {backend_url!r}; "
                f"expected one of {sorted(by_backend_url)}"
            )
        return by_backend_url[backend_url]

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    return calls


def test_mirror_no_drift_when_event_counts_match(runner, monkeypatch):
    """Identical event counts + identical final_text -> exit 0."""
    payload = _make_send_payload(
        final_text="hello world",
        events={"delta": 4, "message": 1, "usage": 1},
    )
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--json",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload_out["diff"]["mode"] == "semantic"
    assert payload_out["diff"]["has_drift"] is False
    assert payload_out["exit_code"] == 0


def test_mirror_drift_when_final_text_differs(runner, monkeypatch):
    """Same event counts but divergent final_text -> exit 5."""
    local_payload = _make_send_payload(final_text="hello", events={"delta": 3, "message": 1})
    upstream_payload = _make_send_payload(
        final_text="hello, world", events={"delta": 3, "message": 1}
    )
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=local_payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=upstream_payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--json",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    assert result.exit_code == 5, result.stdout
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload_out["diff"]["has_drift"] is True
    assert payload_out["diff"]["details"]["final_text_equal"] is False


def test_mirror_drift_when_event_counts_differ(runner, monkeypatch):
    """Diverging per-event-type counts -> exit 5 with per-event delta in details."""
    local_payload = _make_send_payload(final_text="same", events={"delta": 5, "tool_call": 1})
    upstream_payload = _make_send_payload(final_text="same", events={"delta": 5, "tool_call": 2})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=local_payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=upstream_payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--json",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    assert result.exit_code == 5, result.stdout
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    diff_details = payload_out["diff"]["details"]
    assert diff_details["final_text_equal"] is True
    assert diff_details["event_count_diff"] == {
        "tool_call": {"local": 1, "upstream": 2},
    }


def test_mirror_child_failure_returns_exit_6(runner, monkeypatch):
    """If either child exits non-zero, mirror exits 6 without diffing."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(
            returncode=4, stdout=b"", stderr=b"backend unreachable\n"
        ),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--json",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    assert result.exit_code == 6, result.stdout


def test_mirror_ignore_flag_drops_event_types(runner, monkeypatch):
    """``--ignore`` removes a type from the diff even when counts differ."""
    local_payload = _make_send_payload(
        final_text="same", events={"delta": 5, "usage": 1, "noisy": 2}
    )
    upstream_payload = _make_send_payload(
        final_text="same", events={"delta": 5, "usage": 5, "noisy": 9}
    )
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=local_payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=upstream_payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--ignore",
            "noisy",
            "--json",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    # `usage` is in the default ignore list and `noisy` is added explicitly;
    # both should be dropped, leaving no drift.
    assert result.exit_code == 0, result.stdout
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload_out["diff"]["details"]["event_count_diff"] == {}
    assert "noisy" in payload_out["diff"]["details"]["ignored_event_types"]
    assert "usage" in payload_out["diff"]["details"]["ignored_event_types"]


def test_mirror_strict_timing_flags_duration_delta(runner, monkeypatch):
    """``--strict-timing`` flags large wall-clock deltas as drift.

    Children's parent-observed duration is wall-clock around
    ``communicate()``; we simulate divergence by stamping each side's
    duration from its backend URL inside the spawned-proc fake.
    """
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)

    # Patch _run_side so the upstream child reports a 5s wall-clock and the
    # local child a 50ms one — well above the 1000ms strict-timing threshold.
    real_run_side = mirror_module._run_side

    async def fake_run_side(label, profile, backend_url, side_dir, wrapped_args):
        result = await real_run_side(label, profile, backend_url, side_dir, wrapped_args)
        if label == "upstream":
            result.duration_ms = 5000
        else:
            result.duration_ms = 50
        return result

    monkeypatch.setattr(mirror_module, "_run_side", fake_run_side)

    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--strict-timing",
            "--json",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    assert result.exit_code == 5, result.stdout
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload_out["diff"]["details"]["timing_drift"] is True
    assert payload_out["diff"]["details"]["duration_delta_ms"] >= 1000


def test_mirror_spawns_distinct_backend_urls_and_config_dirs(runner, monkeypatch):
    """Each side runs with its own PAW_BACKEND_URL + PAW_CONFIG_DIR + PAW_PROFILE."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    calls = _install_fake_spawns(monkeypatch, procs)
    runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--keep-personas",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    assert len(calls) == 2
    backend_urls = sorted(c["env"]["PAW_BACKEND_URL"] for c in calls)
    assert backend_urls == ["http://127.0.0.1:8000", "https://dev.example.com"]
    config_dirs = {c["env"]["PAW_CONFIG_DIR"] for c in calls}
    assert len(config_dirs) == 2
    profiles = sorted(c["env"]["PAW_PROFILE"] for c in calls)
    assert profiles == ["paw-mirror-local", "paw-mirror-upstream"]


def test_mirror_json_output_schema(runner, monkeypatch):
    """--json payload exposes local, upstream, diff, and exit_code at the top level."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--json",
            "auth",
            "status",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload_out = json.loads(result.stdout.strip().splitlines()[-1])
    assert set(payload_out.keys()) == {"local", "upstream", "diff", "exit_code"}
    for label in ("local", "upstream"):
        side = payload_out[label]
        assert set(side.keys()) == {
            "label",
            "backend_url",
            "profile",
            "exit_code",
            "stdout",
            "stderr",
            "duration_ms",
            "parsed",
        }
    assert set(payload_out["diff"].keys()) == {"mode", "has_drift", "details"}


def test_mirror_falls_back_to_literal_diff_on_non_json_stdout(runner, monkeypatch):
    """Wrapped command without --json -> literal stdout equality diff."""
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=b"local says hi\n", stderr=b""),
        "https://dev.example.com": _FakeProc(
            returncode=0, stdout=b"upstream says ho\n", stderr=b""
        ),
    }
    _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        ["mirror", "--upstream", "https://dev.example.com", "doctor"],
    )
    assert result.exit_code == 5, result.stdout
    # Human mode: verdict line mentions "literal".
    assert "literal" in result.stdout


def test_mirror_requires_wrapped_command(runner):
    """Bare ``paw mirror --upstream URL`` with no wrapped command is a LocalError."""
    result = runner.invoke(app, ["mirror", "--upstream", "https://dev.example.com"])
    assert result.exit_code == 1


def test_mirror_help_text_renders(runner):
    """``paw mirror --help`` exits 0 and mentions --upstream."""
    result = runner.invoke(app, ["mirror", "--help"])
    assert result.exit_code == 0
    assert "upstream" in result.stdout.lower()


def test_mirror_default_cleanup_removes_side_dirs(runner, monkeypatch):
    """Without --keep-personas, per-side config dirs are deleted after the run."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "auth",
            "status",
        ],
    )
    root = paw_config.config_root()
    survivors = [p for p in root.glob(".mirror-*") if p.is_dir()]
    assert survivors == []


def test_mirror_keep_personas_skips_cleanup(runner, monkeypatch):
    """--keep-personas leaves per-side config dirs in place for inspection."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--keep-personas",
            "auth",
            "status",
        ],
    )
    root = paw_config.config_root()
    survivors = sorted(p.name for p in root.glob(".mirror-*") if p.is_dir())
    assert survivors == [".mirror-paw-mirror-local", ".mirror-paw-mirror-upstream"]


def test_mirror_seeds_api_base_url_into_side_state(runner, monkeypatch):
    """Each side's PersonaState.api_base_url is pre-seeded with its backend URL."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    _install_fake_spawns(monkeypatch, procs)
    runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--keep-personas",
            "auth",
            "status",
        ],
    )
    root = paw_config.config_root()
    seeded: dict[str, str] = {}
    for side_dir in root.glob(".mirror-*"):
        # state.json lives under profile_dir = config_root / profile.
        profile_name = side_dir.name.removeprefix(".mirror-")
        state_path = side_dir / profile_name / "state.json"
        assert state_path.exists(), f"missing state file {state_path}"
        body = json.loads(state_path.read_text())
        seeded[body["profile"]] = body["api_base_url"]
    assert seeded == {
        "paw-mirror-local": "http://127.0.0.1:8000",
        "paw-mirror-upstream": "https://dev.example.com",
    }


def test_mirror_local_flag_overrides_default_local_url(runner, monkeypatch):
    """--local URL replaces the default 127.0.0.1:8000 backend for the local side."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://other-host:9000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    calls = _install_fake_spawns(monkeypatch, procs)
    result = runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "--local",
            "http://other-host:9000",
            "auth",
            "status",
        ],
    )
    assert result.exit_code == 0, result.stdout
    backend_urls = sorted(c["env"]["PAW_BACKEND_URL"] for c in calls)
    assert backend_urls == ["http://other-host:9000", "https://dev.example.com"]


def test_mirror_injects_json_flag_into_wrapped_command(runner, monkeypatch):
    """If the wrapped command lacks --json, mirror appends it so both sides emit parseable output."""
    payload = _make_send_payload(final_text="x", events={"delta": 1})
    procs = {
        "http://127.0.0.1:8000": _FakeProc(returncode=0, stdout=payload, stderr=b""),
        "https://dev.example.com": _FakeProc(returncode=0, stdout=payload, stderr=b""),
    }
    calls = _install_fake_spawns(monkeypatch, procs)
    runner.invoke(
        app,
        [
            "mirror",
            "--upstream",
            "https://dev.example.com",
            "conversations",
            "send",
            "hi",
            "--new",
        ],
    )
    for call in calls:
        # argv tail = wrapped command + injected --json.
        assert "--json" in call["args"]

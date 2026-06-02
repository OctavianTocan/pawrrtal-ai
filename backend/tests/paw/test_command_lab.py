"""Tests for ``paw lab`` exploratory benchmark and flow commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, config_root, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
CONV_ID = "11111111-2222-3333-4444-555555555555"
MODEL_ID = "agy-api:google/gemini-3.5-flash-low"


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in persona rooted at the mocked backend."""
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


@pytest.fixture
def stable_uuid(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("app.cli.paw.ids.new_conversation_id", lambda: CONV_ID)
    return CONV_ID


def _assistant_message(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "role": "assistant",
        "content": "done",
        "thinking": "checking",
        "tool_calls": [{"id": "tool-1", "name": "list_dir"}],
        "timeline": [],
        "thinking_duration_seconds": 1,
        "assistant_status": "complete",
        "duration_ms": 987,
    }
    row.update(overrides)
    return row


def _mock_bench_turn(router: respx.MockRouter, conv_id: str = CONV_ID) -> None:
    """Wire the HTTP calls used by one benchmarked chat turn."""
    sse_body = (
        b'data: {"type": "thinking", "content": "checking"}\n\n'
        b'data: {"type": "tool_use", "name": "list_dir", "tool_use_id": "tool-1"}\n\n'
        b'data: {"type": "delta", "content": "done"}\n\n'
        b'data: {"type": "usage", "input_tokens": 4, "output_tokens": 2}\n\n'
        b'data: {"type": "done"}\n\n'
    )
    router.post(f"/api/v1/conversations/{conv_id}").mock(
        return_value=httpx.Response(200, json={"id": conv_id, "title": "paw lab bench"})
    )
    router.post("/api/v1/chat/").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body,
        )
    )
    router.get(f"/api/v1/conversations/{conv_id}/messages").mock(
        return_value=httpx.Response(
            200, json=[{"role": "user", "content": "hello"}, _assistant_message()]
        )
    )
    router.delete(f"/api/v1/conversations/{conv_id}").mock(return_value=httpx.Response(204))


def test_lab_bench_model_records_metrics_and_run_log(
    runner: CliRunner,
    seeded: PersonaState,
    stable_uuid: str,
) -> None:
    """``paw lab bench model`` reports stream metrics and persists a run log."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as router:
        _mock_bench_turn(router, stable_uuid)
        result = runner.invoke(
            app,
            [
                "lab",
                "bench",
                "model",
                "--model",
                MODEL_ID,
                "--prompt",
                "hello",
                "--runs",
                "1",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["model_id"] == MODEL_ID
    assert payload["summary"]["runs"] == 1
    assert payload["measurements"][0]["backend_duration_ms"] == 987
    assert payload["measurements"][0]["event_counts"]["tool_use"] == 1
    assert payload["measurements"][0]["thinking_chars"] == len("checking")
    assert payload["run_path"].startswith(str(config_root()))

    stored = json.loads(Path(payload["run_path"]).read_text(encoding="utf-8"))
    assert stored["run_id"] == payload["run_id"]


def test_lab_runs_show_reads_stored_run(
    runner: CliRunner,
    seeded: PersonaState,
    stable_uuid: str,
) -> None:
    """A benchmark run can be loaded again through ``paw lab runs show``."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as router:
        _mock_bench_turn(router, stable_uuid)
        bench = runner.invoke(
            app,
            [
                "lab",
                "bench",
                "model",
                "--model",
                MODEL_ID,
                "--prompt",
                "hello",
                "--runs",
                "1",
                "--json",
            ],
        )
    assert bench.exit_code == 0, bench.stdout
    run_id = json.loads(bench.stdout)["run_id"]

    shown = runner.invoke(app, ["lab", "runs", "show", run_id, "--json"])

    assert shown.exit_code == 0, shown.stdout
    assert json.loads(shown.stdout)["run_id"] == run_id


def test_lab_bench_model_enforces_default_run_cap(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    """Heavy runs require an explicit opt-in beyond the default cap."""
    result = runner.invoke(
        app,
        [
            "lab",
            "bench",
            "model",
            "--model",
            MODEL_ID,
            "--prompt",
            "hello",
            "--runs",
            "6",
            "--json",
        ],
    )

    assert result.exit_code == 1


def test_lab_flows_lists_and_shows_provider_parity(runner: CliRunner) -> None:
    """Tracked flow definitions are discoverable from the CLI."""
    listed = runner.invoke(app, ["lab", "flows", "ls", "--json"])
    assert listed.exit_code == 0, listed.stdout
    flow_ids = {row["id"] for row in json.loads(listed.stdout)}
    assert "provider-parity" in flow_ids
    assert "telegram-long-chat" in flow_ids

    shown = runner.invoke(app, ["lab", "flows", "show", "provider-parity", "--json"])
    assert shown.exit_code == 0, shown.stdout
    flow = json.loads(shown.stdout)
    assert flow["id"] == "provider-parity"
    assert any("paw lab bench model" in command for command in flow["commands"])


def test_lab_telegram_chat_posts_control_and_turn_messages(
    runner: CliRunner,
    seeded: PersonaState,
    tmp_path: Path,
) -> None:
    """``paw lab telegram chat`` drives Telegram dogfood turns through the API."""
    turns_path = tmp_path / "turns.txt"
    turns_path.write_text("# scenario\nfirst\n\nsecond\n", encoding="utf-8")
    responses = [
        {"accepted": True, "update_id": 1, "chat_id": "333", "external_user_id": "222"},
        {"accepted": True, "update_id": 2, "chat_id": "333", "external_user_id": "222"},
        {"accepted": True, "update_id": 3, "chat_id": "333", "external_user_id": "222"},
        {
            "accepted": True,
            "update_id": 4,
            "chat_id": "333",
            "external_user_id": "222",
            "conversation_id": CONV_ID,
        },
        {
            "accepted": True,
            "update_id": 5,
            "chat_id": "333",
            "external_user_id": "222",
            "conversation_id": CONV_ID,
        },
    ]
    with respx.mock(base_url=MOCK_BACKEND) as router:
        simulate = router.post("/api/v1/channels/telegram/simulate").mock(
            side_effect=[httpx.Response(200, json=row) for row in responses],
        )
        result = runner.invoke(
            app,
            [
                "lab",
                "telegram",
                "chat",
                "--model",
                MODEL_ID,
                "--turns",
                str(turns_path),
                "--new",
                "--verbose",
                "2",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["kind"] == "telegram-chat"
    assert payload["model_id"] == MODEL_ID
    assert payload["summary"]["messages_sent"] == 5
    assert payload["summary"]["conversation_id"] == CONV_ID
    texts = [json.loads(call.request.content)["text"] for call in simulate.calls]
    assert texts == ["/new", f"/model {MODEL_ID}", "/verbose 2", "first", "second"]

    stored = json.loads(Path(payload["run_path"]).read_text(encoding="utf-8"))
    assert stored["run_id"] == payload["run_id"]

"""Tests for ``paw lab runs review`` polish packets."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.commands.lab.storage import write_run
from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
CONV_ID = "11111111-2222-3333-4444-555555555555"
MODEL_ID = "agy-api:google/gemini-3.5-flash-low"


@pytest.fixture
def seeded() -> PersonaState:
    """Persist a logged-in persona rooted at the mocked backend."""
    state = PersonaState(
        profile="default",
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
        default_workspace_id="ws-1",
    )
    state.save()
    jar = load_cookies(cookies_path("default"))
    save_cookies(jar, cookies_path("default"))
    return state


def test_lab_runs_review_builds_polish_packet(
    runner: CliRunner,
    seeded: PersonaState,
) -> None:
    """``paw lab runs review`` packages run evidence for taste feedback."""
    run_id = "review-run"
    write_run(
        "default",
        {
            "run_id": run_id,
            "kind": "telegram-chat",
            "model_id": MODEL_ID,
            "summary": {
                "conversation_id": CONV_ID,
                "max_client_duration_ms": 1234,
                "messages_sent": 1,
            },
            "messages": [
                {
                    "index": 0,
                    "text": "Does this render cleanly?",
                    "client_duration_ms": 1234,
                    "response": {"accepted": True, "conversation_id": CONV_ID},
                }
            ],
        },
    )
    with respx.mock(base_url=MOCK_BACKEND) as router:
        router.get(f"/api/v1/conversations/{CONV_ID}/messages").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"role": "user", "content": "Does this render cleanly?"},
                    {"role": "assistant", "content": "Yes.", "thinking": "Checked markup."},
                ],
            )
        )
        result = runner.invoke(
            app,
            [
                "lab",
                "runs",
                "review",
                run_id,
                "--question",
                "Is the Telegram output clean?",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    packet = json.loads(result.stdout)
    assert packet["taste_question"] == "Is the Telegram output clean?"
    assert packet["conversation_id"] == CONV_ID
    assert packet["run_path"].endswith(f"{run_id}.json")
    assert packet["persisted_messages"][1]["thinking"] == "Checked markup."
    assert "Paw Polish Review" in packet["markdown"]

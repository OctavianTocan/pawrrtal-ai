"""Tests for ``paw jobs`` — scheduled-job CRUD.

Mocks the backend at the HTTP layer with respx. The persona state +
cookie jar are seeded directly per ``test_command_mcp.py`` to keep
the test surface narrow.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from app.cli.paw.config import PersonaState, cookies_path
from app.cli.paw.http import load_cookies, save_cookies
from app.cli.paw.main import app

MOCK_BACKEND = "http://test-backend"
JOB_ID_A = "11111111-1111-1111-1111-111111111111"
JOB_ID_B = "22222222-2222-2222-2222-222222222222"


def _seed_persona(profile: str = "default") -> PersonaState:
    """Persist a logged-in PersonaState rooted at the respx mock backend."""
    state = PersonaState(
        profile=profile,
        env="local",
        api_base_url=MOCK_BACKEND,
        user_id="u1",
        user_email="admin@example.com",
    )
    state.save()
    jar = load_cookies(cookies_path(profile))
    save_cookies(jar, cookies_path(profile))
    return state


@pytest.fixture
def seeded() -> PersonaState:
    return _seed_persona()


def _job_payload(**overrides: Any) -> dict[str, Any]:
    """Build a ``ScheduledJobRead``-shaped row for respx mocks."""
    base: dict[str, Any] = {
        "id": JOB_ID_A,
        "name": "daily summary",
        "cron_expression": "0 9 * * *",
        "fire_at": None,
        "prompt": "summarise today",
        "skill_name": None,
        "target_chat_ids": [],
        "target_conversation_id": None,
        "working_directory": None,
        "last_status": None,
        "last_fired_at": None,
        "last_error": None,
        "is_active": True,
        "created_at": "2026-05-28T00:00:00",
        "updated_at": "2026-05-28T00:00:00",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# paw jobs list
# --------------------------------------------------------------------------- #


def test_jobs_list_returns_json_jobs(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw jobs list --json` round-trips the bare list payload."""
    payload = [_job_payload()]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["jobs", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert isinstance(out, list)
    assert out[0]["id"] == JOB_ID_A
    assert out[0]["name"] == "daily summary"


def test_jobs_list_empty_list_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty job list is a normal state, not an error."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(return_value=httpx.Response(200, json=[]))
        result = runner.invoke(app, ["jobs", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == []


def test_jobs_list_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per job (id, name, schedule, status, active)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(200, json=[_job_payload()])
        )
        result = runner.invoke(app, ["jobs", "list", "--plain"])

    assert result.exit_code == 0, result.stdout
    columns = result.stdout.strip().split("\t")
    assert columns[0] == JOB_ID_A
    assert columns[1] == "daily summary"
    assert columns[2] == "0 9 * * *"
    assert columns[4] == "true"


def test_jobs_list_active_only_filter(runner: CliRunner, seeded: PersonaState) -> None:
    """`--active-only` hides soft-deleted rows client-side."""
    payload = [
        _job_payload(),
        _job_payload(id=JOB_ID_B, name="archived", is_active=False),
    ]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["jobs", "list", "--active-only", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert len(out) == 1
    assert out[0]["id"] == JOB_ID_A


def test_jobs_list_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["jobs", "list", "--json", "--plain"])
    assert result.exit_code == 1


def test_jobs_list_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["jobs", "list", "--json"])
    assert result.exit_code == 3


def test_jobs_list_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["jobs", "list", "--json"])
    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# paw jobs show
# --------------------------------------------------------------------------- #


def test_jobs_show_finds_row_by_id(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw jobs show <id> --json` returns the matching row from the list."""
    payload = [_job_payload(), _job_payload(id=JOB_ID_B, name="other")]
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, ["jobs", "show", JOB_ID_B, "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["id"] == JOB_ID_B
    assert out["name"] == "other"


def test_jobs_show_missing_id_exits_1(runner: CliRunner, seeded: PersonaState) -> None:
    """A non-existent ID surfaces as a LocalError (exit 1)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(200, json=[_job_payload()])
        )
        result = runner.invoke(app, ["jobs", "show", "deadbeef-0000-0000-0000-000000000000"])
    assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# paw jobs create
# --------------------------------------------------------------------------- #


def test_jobs_create_cron_posts_payload(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw jobs create --cron` POSTs the expected body and exits 0 on 201."""
    response_body = _job_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(201, json=response_body)
        )
        result = runner.invoke(
            app,
            [
                "jobs",
                "create",
                "--name",
                "daily summary",
                "--prompt",
                "summarise today",
                "--cron",
                "0 9 * * *",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent["name"] == "daily summary"
    assert sent["prompt"] == "summarise today"
    assert sent["cron_expression"] == "0 9 * * *"
    assert "fire_at" not in sent
    assert sent["target_chat_ids"] == []
    out = json.loads(result.stdout)
    assert out["id"] == JOB_ID_A


def test_jobs_create_at_posts_fire_at(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw jobs create --at` POSTs fire_at and omits cron_expression."""
    response_body = _job_payload(cron_expression=None, fire_at="2026-05-30T09:00:00Z")
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(201, json=response_body)
        )
        result = runner.invoke(
            app,
            [
                "jobs",
                "create",
                "--name",
                "reminder",
                "--prompt",
                "ping",
                "--at",
                "2026-05-30T09:00:00Z",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    sent = json.loads(route.calls.last.request.content)
    assert sent["fire_at"] == "2026-05-30T09:00:00Z"
    assert "cron_expression" not in sent


def test_jobs_create_requires_cron_or_at(runner: CliRunner, seeded: PersonaState) -> None:
    """Calling create without --cron or --at is a local error (exit 1)."""
    result = runner.invoke(app, ["jobs", "create", "--name", "n", "--prompt", "p"])
    assert result.exit_code == 1


def test_jobs_create_rejects_both_cron_and_at(runner: CliRunner, seeded: PersonaState) -> None:
    """Passing both --cron and --at is a local error (exit 1)."""
    result = runner.invoke(
        app,
        [
            "jobs",
            "create",
            "--name",
            "n",
            "--prompt",
            "p",
            "--cron",
            "0 9 * * *",
            "--at",
            "2026-05-30T09:00:00Z",
        ],
    )
    assert result.exit_code == 1


def test_jobs_create_bad_at_format_exits_1(runner: CliRunner, seeded: PersonaState) -> None:
    """A malformed --at value is a local error before the HTTP call."""
    result = runner.invoke(
        app,
        ["jobs", "create", "--name", "n", "--prompt", "p", "--at", "not-a-date"],
    )
    assert result.exit_code == 1


def test_jobs_create_repeated_chat_ids_pack_as_list(
    runner: CliRunner, seeded: PersonaState
) -> None:
    """Repeated --chat-id flags accumulate into target_chat_ids."""
    response_body = _job_payload(target_chat_ids=["111", "222"])
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.post("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(201, json=response_body)
        )
        result = runner.invoke(
            app,
            [
                "jobs",
                "create",
                "--name",
                "broadcast",
                "--prompt",
                "p",
                "--cron",
                "0 9 * * *",
                "--chat-id",
                "111",
                "--chat-id",
                "222",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.stdout
    sent = json.loads(route.calls.last.request.content)
    assert sent["target_chat_ids"] == ["111", "222"]


def test_jobs_create_422_surfaces_as_api_error(runner: CliRunner, seeded: PersonaState) -> None:
    """A 422 from the backend (e.g. invalid cron) surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.post("/api/v1/scheduled-jobs/").mock(
            return_value=httpx.Response(422, json={"detail": "Bad cron"})
        )
        result = runner.invoke(
            app,
            [
                "jobs",
                "create",
                "--name",
                "n",
                "--prompt",
                "p",
                "--cron",
                "bogus",
                "--json",
            ],
        )
    assert result.exit_code == 5


# --------------------------------------------------------------------------- #
# paw jobs delete
# --------------------------------------------------------------------------- #


def test_jobs_delete_requires_yes(runner: CliRunner, seeded: PersonaState) -> None:
    """Without --yes the command is a LocalError (exit 1)."""
    result = runner.invoke(app, ["jobs", "delete", JOB_ID_A])
    assert result.exit_code == 1


def test_jobs_delete_204_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """A 204 deletes the row; JSON output reports deleted=true."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.delete(f"/api/v1/scheduled-jobs/{JOB_ID_A}").mock(
            return_value=httpx.Response(204)
        )
        result = runner.invoke(app, ["jobs", "delete", JOB_ID_A, "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    assert route.called
    out = json.loads(result.stdout)
    assert out == {"deleted": True, "id": JOB_ID_A}


def test_jobs_delete_404_is_soft_noop(runner: CliRunner, seeded: PersonaState) -> None:
    """404 on delete is treated as a soft no-op (deleted=false), exit 0."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/scheduled-jobs/{JOB_ID_A}").mock(
            return_value=httpx.Response(404, json={"detail": "Job not found"})
        )
        result = runner.invoke(app, ["jobs", "delete", JOB_ID_A, "--yes", "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["deleted"] is False
    assert out["reason"] == "not_found"


def test_jobs_delete_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.delete(f"/api/v1/scheduled-jobs/{JOB_ID_A}").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["jobs", "delete", JOB_ID_A, "--yes"])
    assert result.exit_code == 5

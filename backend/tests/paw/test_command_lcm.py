"""Tests for ``paw lcm`` — LCM observability (read-only).

Mocks the backend at the HTTP layer with respx. The persona state is
seeded directly per ``test_command_audit.py`` to keep the test surface
narrow.
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
CONV_ID = "6c87aa72-1b3c-4f0e-9f4d-2b8a7c5a1d11"
MESSAGE_ID_A = "11111111-1111-1111-1111-111111111111"
SUMMARY_ID_A = "22222222-2222-2222-2222-222222222222"


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


def _context_payload(*, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build an ``LCMContextDebugResponse``-shaped payload for respx mocks."""
    default_items: list[dict[str, Any]] = [
        {
            "ordinal": 0,
            "item_kind": "summary",
            "item_id": SUMMARY_ID_A,
            "role": None,
            "preview": "Earlier turns compacted into a depth-1 summary.",
            "token_count": 120,
            "summary_depth": 1,
            "summary_kind": "leaf",
            "source_count": 4,
        },
        {
            "ordinal": 1,
            "item_kind": "message",
            "item_id": MESSAGE_ID_A,
            "role": "user",
            "preview": "What is LCM and why do we need it?",
            "token_count": 12,
            "summary_depth": None,
            "summary_kind": None,
            "source_count": None,
        },
    ]
    resolved = default_items if items is None else items
    message_count = sum(1 for i in resolved if i.get("item_kind") == "message")
    summary_count = sum(1 for i in resolved if i.get("item_kind") == "summary")
    estimated = sum(i.get("token_count") or 0 for i in resolved)
    return {
        "conversation_id": CONV_ID,
        "lcm_enabled": True,
        "fresh_tail_count": 64,
        "item_count": len(resolved),
        "message_count": message_count,
        "summary_count": summary_count,
        "estimated_tokens": estimated,
        "items": resolved,
        "settings": {
            "lcm_enabled": True,
            "fresh_tail_count": 64,
            "leaf_chunk_tokens": 1024,
            "incremental_max_depth": 3,
        },
    }


# --------------------------------------------------------------------------- #
# paw lcm context
# --------------------------------------------------------------------------- #


def test_lcm_context_returns_json_payload(runner: CliRunner, seeded: PersonaState) -> None:
    """`paw lcm context <id> --json` round-trips the full debug payload."""
    payload = _context_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID, "--json"])

    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out["conversation_id"] == CONV_ID
    assert out["item_count"] == 2
    assert out["items"][1]["role"] == "user"


def test_lcm_context_forwards_fresh_tail_count(runner: CliRunner, seeded: PersonaState) -> None:
    """--fresh-tail-count is forwarded as the `fresh_tail_count` query param."""
    payload = _context_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(
            app, ["lcm", "context", CONV_ID, "--fresh-tail-count", "32", "--json"]
        )

    assert result.exit_code == 0, result.stdout
    assert route.called
    sent_url = str(route.calls.last.request.url)
    assert "fresh_tail_count=32" in sent_url


def test_lcm_context_omits_unset_fresh_tail_count(runner: CliRunner, seeded: PersonaState) -> None:
    """Omitting --fresh-tail-count keeps it off the wire (no silent override)."""
    payload = _context_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        route = r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID, "--json"])

    assert result.exit_code == 0, result.stdout
    sent_url = str(route.calls.last.request.url)
    assert "fresh_tail_count" not in sent_url


def test_lcm_context_human_view_renders(runner: CliRunner, seeded: PersonaState) -> None:
    """Default human view surfaces the summary header + per-item table."""
    payload = _context_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID])

    assert result.exit_code == 0, result.stdout
    assert CONV_ID in result.stdout
    assert "lcm_enabled" in result.stdout
    assert "fresh_tail_count" in result.stdout
    assert "estimated_tokens" in result.stdout
    assert "ORD" in result.stdout
    assert "KIND" in result.stdout
    assert "PREVIEW" in result.stdout
    assert "What is LCM" in result.stdout


def test_lcm_context_plain_tsv_shape(runner: CliRunner, seeded: PersonaState) -> None:
    """`--plain` emits one TSV row per item with the expected columns."""
    payload = _context_payload()
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID, "--plain"])

    assert result.exit_code == 0, result.stdout
    lines = [line for line in result.stdout.splitlines() if line]
    assert len(lines) == 2
    summary_cols = lines[0].split("\t")
    assert summary_cols[0] == "0"
    assert summary_cols[1] == "summary"
    assert summary_cols[2] == SUMMARY_ID_A
    assert summary_cols[5] == "1"  # summary_depth
    assert summary_cols[6] == "leaf"  # summary_kind
    message_cols = lines[1].split("\t")
    assert message_cols[1] == "message"
    assert message_cols[3] == "user"


def test_lcm_context_empty_items_succeeds(runner: CliRunner, seeded: PersonaState) -> None:
    """An empty context payload is a normal state, not an error."""
    payload = _context_payload(items=[])
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID])

    assert result.exit_code == 0, result.stdout
    assert "no LCM context items yet" in result.stdout


def test_lcm_context_rejects_both_json_and_plain(runner: CliRunner, seeded: PersonaState) -> None:
    """--json + --plain is a usage error (LocalError -> exit 1)."""
    result = runner.invoke(app, ["lcm", "context", CONV_ID, "--json", "--plain"])
    assert result.exit_code == 1


def test_lcm_context_rejects_out_of_range_fresh_tail(
    runner: CliRunner, seeded: PersonaState
) -> None:
    """Out-of-range --fresh-tail-count is a local error (exit 1) before any HTTP call."""
    result = runner.invoke(app, ["lcm", "context", CONV_ID, "--fresh-tail-count", "-1"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["lcm", "context", CONV_ID, "--fresh-tail-count", "9999"])
    assert result.exit_code == 1


def test_lcm_context_401_exits_3(runner: CliRunner, seeded: PersonaState) -> None:
    """A 401 surfaces as AuthError (exit 3)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(401, json={"detail": "Not authenticated"})
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID, "--json"])
    assert result.exit_code == 3


def test_lcm_context_404_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """A 404 (conversation not found / not yours) surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(404, json={"detail": "Conversation not found"})
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID, "--json"])
    assert result.exit_code == 5


def test_lcm_context_500_exits_5(runner: CliRunner, seeded: PersonaState) -> None:
    """An unexpected 500 surfaces as ApiError (exit 5)."""
    with respx.mock(base_url=MOCK_BACKEND, assert_all_called=False) as r:
        r.get(f"/api/v1/lcm/conversations/{CONV_ID}/context").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        result = runner.invoke(app, ["lcm", "context", CONV_ID, "--json"])
    assert result.exit_code == 5

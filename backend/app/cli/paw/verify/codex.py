"""End-to-end Codex provider verification scenario.

The headline scenario for ``paw verify``. Drives the real chat surface
(``POST /api/v1/conversations/{uuid}`` -> ``POST /api/v1/chat/`` streamed
-> ``GET /api/v1/conversations/{id}`` -> ``GET /api/v1/conversations/{id}/messages``
-> turn 2 -> thread-resume verification -> cleanup) and asserts on every
observable property a Codex turn touches.

The scenario itself uses paw's own building blocks — ``PawClient``,
``PawClient.stream_events``, ``new_conversation_id`` — so frame-boundary
bugs in the SSE framer are caught the same way they would be by the
frontend.
"""

from __future__ import annotations

import time
from typing import Any

from app.cli.paw import ids
from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult

CODEX_MODEL = "openai-codex:openai/gpt-5.5"
TURN_1 = "Say hi in exactly two words."
TURN_2 = "Now say bye in exactly two words."

# A turn must complete within this wall-clock budget for the scenario
# to consider it healthy. Codex normally streams within a few seconds;
# anything over a minute means a hang, not slowness.
TURN_BUDGET_MS = 60_000

# PawClient default is 60s; bump well above ``TURN_BUDGET_MS`` so the
# HTTP transport never times out before the per-turn budget check fires.
SCENARIO_HTTP_TIMEOUT_SECONDS = 120.0

# A successful chat round-trip persists exactly two ``chat_messages`` rows
# per turn — the user prompt and the assistant reply — so any value below
# this means the post-turn fetch races the writer or the writer dropped a row.
MIN_MESSAGES_AFTER_TURN_1 = 2


def _extract_models(payload: Any) -> list[dict[str, Any]]:
    """Return the model list regardless of whether the API wraps it.

    The catalog endpoint has shipped both shapes (``{"models": [...]}`` and a
    bare list) at various points; accept either so this scenario doesn't
    fail on an envelope change.
    """
    if isinstance(payload, dict):
        models = payload.get("models", [])
        return models if isinstance(models, list) else []
    if isinstance(payload, list):
        return payload
    return []


def _find_codex_entry(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Locate the Codex model catalog entry by ``model_id`` or legacy ``id``."""
    for m in models:
        if not isinstance(m, dict):
            continue
        if m.get("model_id") == CODEX_MODEL or m.get("id") == CODEX_MODEL:
            return m
    return None


async def _check_catalog(client: PawClient, r: ScenarioResult) -> dict[str, Any] | None:
    """Verify the Codex model is in the catalog + authenticated.

    Returns the catalog entry so caller can short-circuit when missing.
    """
    models_resp = (await client.request("GET", "/api/v1/models")).json()
    models = _extract_models(models_resp)
    r.artifacts["models_count"] = len(models)
    entry = _find_codex_entry(models)
    r.add(
        "codex_model_in_catalog",
        entry is not None,
        detail=f"no entry for {CODEX_MODEL}" if entry is None else "",
    )
    if entry is None:
        return None
    r.add(
        "codex_model_authenticated",
        bool(entry.get("authenticated", True)),
        detail=str(entry),
    )
    return entry


async def _create_conversation(client: PawClient, r: ScenarioResult) -> str:
    """POST a new conversation with a client-generated UUID. Returns the id."""
    conv_id = ids.new_conversation_id()
    create_resp = await client.request(
        "POST",
        f"/api/v1/conversations/{conv_id}",
        json_body={"id": conv_id, "title": "paw verify codex"},
        expect=(200, 201),
    )
    r.add(
        "conversation_created",
        create_resp.status_code in (200, 201),
        detail=f"status={create_resp.status_code}",
    )
    return conv_id


async def _stream_turn(client: PawClient, conv_id: str, text: str) -> list[dict[str, Any]]:
    """Drive one chat turn end-to-end; return the full event list."""
    return [
        ev
        async for ev in client.stream_events(
            method="POST",
            url="/api/v1/chat/",
            json_body={
                "question": text,
                "model_id": CODEX_MODEL,
                "conversation_id": conv_id,
            },
        )
    ]


def _assert_turn_1(r: ScenarioResult, events: list[dict[str, Any]], duration_ms: int) -> None:
    """Apply turn-1 specific assertions (content, errors, done, budget, text)."""
    deltas_or_messages = [e for e in events if e.get("type") in ("delta", "message")]
    errors = [e for e in events if e.get("type") == "error"]
    done = any(e.get("type") == "done" for e in events)
    final_text = "".join(
        e.get("content", "") for e in deltas_or_messages if isinstance(e.get("content"), str)
    )
    r.add(
        "turn_1_has_content",
        len(deltas_or_messages) > 0,
        detail=f"events={len(deltas_or_messages)}",
    )
    r.add(
        "turn_1_no_errors",
        len(errors) == 0,
        detail=f"first_error={errors[0] if errors else None}",
    )
    r.add("turn_1_terminates_with_done", done)
    r.add(
        "turn_1_within_budget",
        duration_ms < TURN_BUDGET_MS,
        detail=f"{duration_ms}ms (budget {TURN_BUDGET_MS}ms)",
    )
    r.add(
        "turn_1_final_text_nonempty",
        bool(final_text.strip()),
        detail=repr(final_text[:80]),
    )


def _assert_turn_2(r: ScenarioResult, events: list[dict[str, Any]]) -> None:
    """Apply turn-2 assertions (lighter than turn 1 — same conversation already proven)."""
    deltas_2 = [e for e in events if e.get("type") in ("delta", "message")]
    errors_2 = [e for e in events if e.get("type") == "error"]
    r.add("turn_2_has_content", len(deltas_2) > 0, detail=f"events={len(deltas_2)}")
    r.add(
        "turn_2_no_errors",
        len(errors_2) == 0,
        detail=f"first_error={errors_2[0] if errors_2 else None}",
    )


async def _assert_conversation_state(
    client: PawClient, r: ScenarioResult, conv_id: str
) -> str | None:
    """Verify model + codex_thread_id were persisted after turn 1. Returns thread id."""
    detail_1 = (await client.request("GET", f"/api/v1/conversations/{conv_id}")).json()
    r.artifacts["conversation_detail_after_turn_1"] = detail_1
    r.add(
        "conversation_model_matches",
        detail_1.get("model_id") == CODEX_MODEL,
        detail=f"got={detail_1.get('model_id')}",
    )
    thread_id = detail_1.get("codex_thread_id")
    r.add(
        "codex_thread_id_persisted",
        bool(thread_id),
        detail=f"thread_id={thread_id}",
    )
    return thread_id if isinstance(thread_id, str) else None


async def _assert_messages(client: PawClient, r: ScenarioResult, conv_id: str) -> None:
    """Verify two persisted messages (user + assistant) with a complete assistant row."""
    msgs = (await client.request("GET", f"/api/v1/conversations/{conv_id}/messages")).json()
    r.artifacts["messages_count"] = len(msgs) if isinstance(msgs, list) else None
    is_list = isinstance(msgs, list)
    enough_messages = is_list and len(msgs) >= MIN_MESSAGES_AFTER_TURN_1
    r.add(
        "messages_persisted",
        enough_messages,
        detail=f"got {len(msgs) if is_list else 'N/A'}",
    )
    if not enough_messages:
        return
    assistant = msgs[-1]
    r.add(
        "assistant_status_complete",
        assistant.get("assistant_status") == "complete",
        detail=f"status={assistant.get('assistant_status')}",
    )
    r.add(
        "assistant_content_nonempty",
        bool((assistant.get("content") or "").strip()),
        detail=f"content_len={len(assistant.get('content') or '')}",
    )


async def _cleanup(client: PawClient, r: ScenarioResult, conv_id: str, *, keep: bool) -> None:
    """Delete the conversation unless ``keep`` (then record the kept id)."""
    if keep:
        r.add("conversation_kept_per_flag", True, detail=conv_id)
        return
    await client.request(
        "DELETE",
        f"/api/v1/conversations/{conv_id}",
        expect=(200, 204),
    )
    r.add("conversation_cleanup", True)


async def run_codex_scenario(
    state: PersonaState,
    client: PawClient,
    *,
    keep_conversation: bool = False,
) -> ScenarioResult:
    """Drive a two-turn Codex chat and assert on every observable property."""
    r = ScenarioResult(name="codex")

    # 1. Models catalog.
    entry = await _check_catalog(client, r)
    if entry is None:
        return r

    # 2. Create conversation (UUID-first flow).
    conv_id = await _create_conversation(client, r)

    # 3. Turn 1: stream.
    t0 = time.monotonic()
    events_1 = await _stream_turn(client, conv_id, TURN_1)
    duration_1_ms = int((time.monotonic() - t0) * 1000)
    r.artifacts["turn_1_events"] = events_1
    r.artifacts["turn_1_ms"] = duration_1_ms
    _assert_turn_1(r, events_1, duration_1_ms)

    # 4. Conversation row + codex_thread_id.
    thread_id_1 = await _assert_conversation_state(client, r, conv_id)

    # 5. Messages.
    await _assert_messages(client, r, conv_id)

    # 6. Turn 2 — same conversation_id.
    events_2 = await _stream_turn(client, conv_id, TURN_2)
    r.artifacts["turn_2_events"] = events_2
    _assert_turn_2(r, events_2)

    # 7. Thread resumed (not recreated). Pin the exact value, not just non-null —
    #    a regression that mints a fresh thread per turn would otherwise pass.
    detail_2 = (await client.request("GET", f"/api/v1/conversations/{conv_id}")).json()
    thread_id_2 = detail_2.get("codex_thread_id")
    r.add(
        "codex_thread_id_unchanged_on_resume",
        thread_id_2 == thread_id_1 and thread_id_1 is not None,
        detail=f"before={thread_id_1!r} after={thread_id_2!r}",
    )

    # 8. Cleanup.
    await _cleanup(client, r, conv_id, keep=keep_conversation)

    return r

---
# pawrrtal-yv54
title: 'bug(paw): live E2E suite green only against Postgres — SQLite chat path failing'
status: completed
type: bug
priority: normal
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-28T00:18:27Z
---

When PAW_E2E=1 runs against a SQLite backend the chat-roundtrip path fails. Postgres is green. Need to diagnose whether the chat router or persistence assumes Postgres semantics (JSONB? array contains?). Parent: pawrrtal-6cnv.

## Summary of Changes

**Root cause.** The chat router passed the request-scoped `AsyncSession` from
`Depends(get_async_session)` into `ChatTurnInput.db_session`. `StreamingResponse`
keeps the response body iterating long after the route handler returns, so by
the time `_finalize_turn` ran, aiosqlite's underlying connection had been
torn down by the dependency context cleanup. Subsequent `session.execute()` /
rollback calls raised `sqlite3.OperationalError: no active connection` and the
assistant placeholder row stayed stuck in `status="streaming"`. Postgres
masked this because pool checkout + `pool_pre_ping` transparently reconnects
on a dead socket; aiosqlite does not.

**Fix.** Drop `db_session=session` from the `ChatTurnInput(...)` construction
in `backend/app/api/chat.py`. The turn runner's `_turn_session` helper already
falls back to opening its own `async_session_maker()` session when
`db_session` is `None` — the Telegram surface has always used this path, which
is why Telegram traffic on SQLite never hit the bug. The route handler still
uses the request session for the pre-stream work (conversation lookup, model
switch, workspace gate, cost budget, MCP config load) — that work happens
inside the route handler's call stack, where the session is fully alive.

**Tests.** Added `backend/tests/test_chat_sqlite_session_lifecycle.py` with
two regressions:

1. `test_chat_router_does_not_pass_request_session_into_turn_input` — locks
   in the architectural invariant by patching `ChatTurnInput` to capture
   kwargs and asserting `db_session` is absent / `None`.
2. `test_chat_finalizes_assistant_status_on_sqlite` — end-to-end: drives a
   chat turn with a fake provider on the in-memory SQLite engine and asserts
   the assistant row reaches `status="complete"`. Before the fix this row
   stayed in `streaming` because `_finalize_turn` ran on a dead connection.

Also taught `backend/tests/conftest.py`'s `db_session` fixture to rebind
`app.channels.turn_runner.async_session_maker` to the in-memory engine, so
the runner's self-opened sessions see the same tables as the request session
in tests.

**Out of scope but observed.** `paw verify chat-roundtrip --model
litellm:openai/gpt-4o-mini` still fails the live E2E because the scenario
forwards `reasoning_effort="high"` and LiteLLM rejects the parameter for
gpt-4o-mini (`UnsupportedParamsError`). That's a separate bug — the chat
router does not catalog-validate `request.reasoning_effort` against the
selected model before forwarding it — and is unrelated to the SQLite/aiosqlite
session lifecycle issue described above. File a follow-up bean for that.

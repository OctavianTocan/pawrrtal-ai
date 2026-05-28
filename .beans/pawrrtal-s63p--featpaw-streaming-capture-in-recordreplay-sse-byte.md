---
# pawrrtal-s63p
title: 'feat(paw): streaming capture in record/replay (SSE bytes)'
status: completed
type: feature
priority: low
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-28T00:03:34Z
---

paw record/replay captures HTTP requests + responses but not the raw SSE byte stream. Add a dedicated writer that captures provider-emitted delta/done events frame-by-frame so replay can drive offline tests bit-for-bit. Parent: pawrrtal-6cnv.

## Summary of Changes

- `backend/app/cli/paw/sse.py`: `stream_chat_events` now takes an optional `on_raw_frame: RawFrameTap | None` callback that fires with every non-empty SSE frame (data, comment, `[DONE]` sentinel) before parsing. Purely additive — default behaviour unchanged when the tap is unset.
- `backend/app/cli/paw/http.py`: `PawClient` exposes `is_recording`, `record_sse_frame(url, frame)`, and `make_sse_tap(url)`. When `PAW_RECORD` is active, `make_sse_tap` returns a closure that writes one `{"type": "sse", "url": ..., "frame_b64": ..., "ts": ...}` row per frame to the same JSONL file the HTTP envelope hooks already use.
- `backend/app/cli/paw/commands/conversations.py`: `_send_turn` wires the tap into `stream_chat_events`. No new branches in the hot path; the tap is just a callback parameter.
- `backend/app/cli/paw/commands/replay.py`: detects `type=sse` rows, reconstructs the wire body per URL by joining captured frames with `\n\n` + trailing delimiter, and mounts a streaming `httpx.Response` so the same `stream_chat_events` framer re-runs offline. Multi-call flows consume bodies in recorded order.
- `backend/tests/paw/test_record_replay_sse.py`: new roundtrip test — records an SSE-emitting chat turn against a respx-mocked upstream, asserts one `type=sse` row per `data:` frame (delta×2 + usage + `[DONE]`), then replays the fixture and verifies the consumer reconstructs deltas, final text, and `codex_thread_id` without any upstream available.
- `.claude/skills/paw/SKILL.md`: drop the "streaming capture" line from Open follow-up beans.

## Verification

- `uv run pytest tests/paw/test_record_replay_sse.py -v` → 2 passed.
- `uv run pytest tests/paw` → 106 passed (104 pre-existing + 2 new).
- `uv run ruff check app/cli/paw tests/paw/test_record_replay_sse.py` → clean.
- `uv run mypy app` → clean (287 files).

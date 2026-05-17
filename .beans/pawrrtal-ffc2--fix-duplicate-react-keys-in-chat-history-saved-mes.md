---
# pawrrtal-ffc2
title: Fix duplicate React keys in chat history (saved messages)
status: completed
type: bug
priority: normal
created_at: 2026-05-17T16:42:29Z
updated_at: 2026-05-17T16:48:18Z
---

ChatView builds message keys from role + thinking_started_at + content slice. Persisted messages have no thinking_started_at, so the key falls back to 'role:saved:<content>', which collides whenever the same content recurs (e.g. user sends 'Yo' twice). Fix by including the array index for saved messages so each row gets a unique key.

## Summary of Changes

Replaced the content-derived key in `frontend/features/chat/ChatView.tsx` (`role:thinking_started_at|'saved':content.slice(0,80)`) with `role:thinking_started_at|'saved-<index>'`.

`thinking_started_at` is only set during live streaming. Persisted server history leaves it undefined, so the old key collapsed to `role:saved:<content>` and collided whenever the same content recurred (e.g. user typing "Yo" twice, or the assistant returning the same Gemini 400 error body twice). The new `saved-<index>` fallback is stable across re-renders within a conversation (chat history is append-only) and uniquely identifies each row.

The proper long-term fix is to add a stable server-provided `id` to the `ChatMessage` interface and have the persistence layer hydrate it — flagged for follow-up but out of scope for this fix.

Verified: `bunx biome check` clean on the file, `bunx tsc --noEmit` clean across the project.

## Follow-up: tool-call duplicate keys

Same warning class also fired from `ChainOfThought.tsx` with keys like `tool-call-list_dir-0`. Two issues stacked:

1. **Root cause (backend):** `backend/app/core/providers/gemini_provider.py` built tool call ids as `call-{fn_name}-{N}` where N was a counter local to one `stream()` call. The agent loop calls `stream()` fresh on every iteration, so the counter restarted to 0 each turn — identical tool names called across iterations collided (e.g. iteration=1 `list_dir` and iteration=2 `list_dir` both got `call-list_dir-0`). Fixed by using `uuid.uuid4().hex[:12]` as the suffix instead of a counter, giving globally-unique ids across the whole session. `_tool_calls_from_chunk`'s `start_index` parameter is now unused and was dropped.

2. **Defense in depth (frontend):** `ChainOfThought.tsx:162` now suffixes every step key with the map index. Thinking steps had no id at all (content-derived key), and old persisted history was written with the colliding counter ids and would still render duplicates without a DB backfill.

Verified: `bunx biome check` clean, `bunx tsc --noEmit` clean, `ruff check` clean, `pytest tests/test_gemini_stream_fn.py tests/test_provider_native_replay_state.py` 9/9 passed.

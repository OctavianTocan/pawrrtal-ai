---
# pawrrtal-5m4f
title: Telegram surfaces non-text outcomes + tool-call traces
status: in-progress
type: bug
priority: normal
created_at: 2026-05-15T07:08:07Z
updated_at: 2026-05-17T09:41:26Z
---

Telegram chat shows stuck hourglass when agent terminates without text (e.g. Gemini loops tools, hits max_iterations). TelegramChannel.deliver only handles delta events, drops agent_terminated/error. Also: no logs identify which tool the model is looping on. Three pieces: (1) Telegram channel surfaces agent_terminated/error/empty outcomes by editing placeholder; (2) agent_loop emits INFO traces per tool call with name+args; (3) turn_runner logs per-channel event breakdown.

## Summary of Changes

Branch: `fix/telegram-error-surfacing-and-tool-traces`.

**Piece 1 — Telegram surfaces non-text outcomes** (`backend/app/channels/telegram.py`)
`TelegramChannel.deliver` now watches for `agent_terminated` and `error` events and replaces the ⏳ placeholder with the human-readable copy (prefixed ⚠️ / ❌). When the stream produces nothing at all, a fallback message points the user at `backend/app.log`. Single final `edit_message_text` call guarantees the placeholder is always replaced. Three new tests cover `agent_terminated`-only, `agent_terminated`-after-text, and `error`-only paths.

**Piece 2 — Tool-call traces** (`backend/app/core/agent_loop/loop.py`)
Each tool call emits a `TOOL_CALL_START` INFO line (iteration, name, tool_call_id, args truncated to 500 chars) and a `TOOL_CALL_RESULT` line (is_error, duration_ms, result_len). Full result body is at DEBUG. Per-iteration: `LOOP_ITERATION iteration=N stop_reason=X tool_calls=N`. Extracted `_execute_and_log_tool_call` helper — net-reduced `_run_loop` complexity (C901 20→18, PLR0912 21→18, PLR0915 78→68) but it still exceeds budget; sibling refactor needed.

**Piece 3 — Per-channel event breakdown** (`backend/app/channels/turn_runner.py`)
`_EventCounter` now records per-type counts via `.record(event)`. The aggregate `*_OUT` log line gained a `breakdown=[delta=12 tool_use=3 tool_result=3 ...]` field, so the postmortem answers 'what kinds of N events?' instead of just 'how many?'.

**Tests**: `tests/test_telegram_channel.py` updated + extended. Full suite `-k 'turn_runner or telegram or agent_loop or chat'` passes (101 passed, 1 skipped).



## Follow-up Update - 2026-05-17

Implemented the Telegram presentation split requested in chat: tool calls are collected into one editable tool-trace message with icon, tool name, argument key list, and escaped JSON input; thinking text is sent/edited as a separate italic HTML message; final assistant text is sent as a separate final Telegram message. Telegram bot handling now passes reply metadata through both immediate placeholder replies and channel delivery, so generated messages reply to the incoming Telegram message and preserve forum thread routing. Added focused tests for final-message sending, detailed tool traces, italic thinking updates, and reply parameters.

Touched: backend/app/channels/telegram.py, backend/app/channels/telegram_delivery.py, backend/app/integrations/telegram/bot.py, backend/app/integrations/telegram/tool_icons.py, backend/tests/test_telegram_channel.py.

Verification: node scripts/check-file-lines.mjs; python3 scripts/check-nesting.py; backend ruff check for the touched Telegram modules/tests; backend pytest tests/test_telegram_channel.py tests/test_send_message_tool.py tests/test_verbose_filter.py (83 passed).



## Follow-up Update - Live Tool Streaming

Confirmed the trace matched a real buffering issue below Telegram: backend/app/core/agent_loop/loop.py collected provider events inside _stream_with_retry and replayed them only after the provider emitted its terminal done event. That meant Telegram could not see tool_use events while a model was still in a tool-call turn. Updated the agent loop to yield translated provider events as they arrive while still capturing terminal assistant content for persistence. Also changed the Gemini StreamEvent adapter to emit tool_use from tool_call_end so the event includes tool arguments instead of an empty input object. Added a regression test that blocks provider done and asserts tool_call_start/tool_call_end have already streamed.

Verification: python3 scripts/check-nesting.py; node scripts/check-file-lines.mjs; backend py_compile for touched loop/provider/tests; ruff check for touched backend files; backend pytest tests/test_agent_loop_scenarios.py tests/test_agent_loop.py tests/test_gemini_stream_fn.py tests/test_telegram_channel.py tests/test_send_message_tool.py tests/test_verbose_filter.py (105 passed).

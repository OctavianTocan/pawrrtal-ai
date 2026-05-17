---
# pawrrtal-07ru
title: Fix React duplicate-key warning for tool-call-{name}-0 across agent iterations
status: completed
type: bug
priority: high
created_at: 2026-05-17T21:04:12Z
updated_at: 2026-05-17T21:05:24Z
---

Gemini provider resets tool_call_id counter on each StreamFn iteration, producing duplicate IDs like call-list_dir-0 across iterations. Frontend keys tool steps by these IDs (ChainOfThought.tsx:191 → key=tool-call-list_dir-0), causing dev-console React duplicate-key warnings and (worse) collapsing distinct tool calls in the toolCallsById Map.


## Summary of Changes

Fixed in `backend/app/core/providers/gemini_provider.py:200` by appending an 8-char uuid4 hex suffix to the generated `tool_call_id`:

```python
tool_call_id = f"call-{fn_name}-{start_index + len(calls)}-{uuid.uuid4().hex[:8]}"
```

This makes IDs unique across every StreamFn call within a turn, so the React `key` constructed in `frontend/features/chat/components/ChainOfThought.tsx:191` (`tool-${item.call.id}`) no longer collides between agent-loop iterations. Gemini matches function calls to function responses by ordinal position, not by our ID, so the suffix is invisible to the model.

Ran `tests/test_provider_native_replay_state.py`, `tests/test_gemini_stream_fn.py`, and `tests/test_gemini_manual_function_calling.py` — all green. Ruff clean.

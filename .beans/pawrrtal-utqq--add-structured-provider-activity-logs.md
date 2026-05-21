---
# pawrrtal-utqq
title: Add structured provider activity logs
status: completed
type: task
priority: normal
created_at: 2026-05-21T12:19:20Z
updated_at: 2026-05-21T12:24:42Z
---

Add Gemini CLI-style structured operator logging to the other model providers so long turns show stream activity, tool/progress events, usage, and errors in backend logs.

## Summary of Changes

- Added shared provider stream logging helper for bounded structured StreamEvent logs.
- Wired the helper into Claude, native Gemini, xAI, OpenCode Go, and LiteLLM public provider streams.
- Preserved bounded snippets and metadata-only summaries for text/thinking/errors, tool use/results, usage, and unknown event shapes.

## Verification

- cd backend && uv run ruff check app/core/providers/_stream_logging.py app/core/providers/claude_provider.py app/core/providers/gemini_provider.py app/core/providers/xai_provider.py app/core/providers/opencode_go_provider.py app/core/providers/litellm_provider.py
- cd backend && uv run pytest tests/test_gemini_cli_provider.py tests/test_gemini_stream_fn.py tests/test_xai_stream_fn.py tests/test_xai_provider_translation.py tests/test_opencode_go_provider.py tests/test_litellm_provider.py tests/test_claude_provider.py tests/test_claude_provider_pr05.py tests/test_claude_provider_history_prefix.py

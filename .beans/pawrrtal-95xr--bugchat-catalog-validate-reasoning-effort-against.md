---
# pawrrtal-95xr
title: 'bug(chat): catalog-validate reasoning_effort against selected model before forwarding to provider'
status: todo
type: bug
priority: high
created_at: 2026-05-28T00:21:28Z
updated_at: 2026-05-28T00:21:28Z
---

paw verify chat-roundtrip surfaced this: scenario forwards reasoning_effort='high' to litellm:openai/gpt-4o-mini and LiteLLM raises UnsupportedParamsError. The chat router doesn't catalog-validate request.reasoning_effort against the selected model's capabilities before passing through. Surfaced during Task 1 (pawrrtal-yv54). Fix: gate reasoning_effort to models whose catalog entry advertises reasoning support; drop or warn on incompatible combinations.

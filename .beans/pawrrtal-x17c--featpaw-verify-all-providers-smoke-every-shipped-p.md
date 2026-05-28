---
# pawrrtal-x17c
title: 'feat(paw): verify all-providers — smoke every shipped provider in one job'
status: todo
type: feature
priority: high
created_at: 2026-05-28T09:14:50Z
updated_at: 2026-05-28T09:14:50Z
---

From paw v3 brainstorm Thread 4. Iterate over the catalog, pick one canonical model per provider (claude, gemini, gemini_cli, xai, opencode_go, agy_cli, openai_codex, litellm-wrapped), run chat-roundtrip against each, aggregate exits. Today only Codex has a dedicated verify suite; other providers are tested only when someone manually passes --model. CI gets one failing-provider job instead of relying on chat-roundtrip catching a single model.

---
# pawrrtal-kexi
title: Gemini provider doesn't emit usage events; cost_ledger stays empty
status: todo
type: bug
priority: normal
created_at: 2026-05-17T17:36:30Z
updated_at: 2026-05-17T17:36:30Z
---

The Gemini provider's StreamFn never yields an LLMUsageEvent (or equivalent 'usage' stream event), so chat_aggregator.total_input_tokens / total_output_tokens stay 0 for every Gemini turn. As a result, record_turn_cost_if_enabled early-returns and no cost_ledger row is written. Consequences: (1) no per-user cost cap applies to Gemini turns, (2) /status shows zero tokens for Gemini-only conversations, (3) the cost API can't report Gemini spend. Verified by inspecting the live pawrrtal.db: 48 Telegram messages on conversation c067d1bc (Gemini) → 0 cost_ledger rows; web conversations on Claude → ledger rows present. Fix should emit a 'usage' event with input_tokens/output_tokens from Gemini's GenerateContentResponse.usage_metadata at the terminal LLMDoneEvent.

---
# pawrrtal-6q96
title: 'Telegram: thread reasoning_effort through ChatTurnInput so xAI thinking actually streams'
status: todo
type: bug
priority: high
created_at: 2026-05-19T12:20:33Z
updated_at: 2026-05-19T12:21:49Z
---

Telegram bot builds ChatTurnInput without reasoning_effort, so xAI (and any other reasoning-capable provider) is invoked with reasoning_effort=None. The xAI provider then omits the field from the request and 'lets xAI pick the model default' — which for many models means no reasoning_content streams back, so users see no chain-of-thought even at /verbose 2.


## Evidence

- Telegram bot build site: \`backend/app/integrations/telegram/bot.py:251-272\` — \`ChatTurnInput(...)\` is constructed with \`verbose_level=...\` but no \`reasoning_effort\` kwarg. Field defaults to \`None\` per \`backend/app/channels/turn_runner.py:83\`.
- Web parity reference: \`backend/app/api/chat.py:362\` does \`reasoning_effort=request.reasoning_effort\`.
- xAI provider behaviour: \`backend/app/core/providers/xai_provider.py:116-134\` (\`_map_reasoning_effort\`) returns \`None\` for \`effort is None\`; the field is then omitted from the \`chat.create(...)\` call at \`xai_provider.py:231-236\`. Per the docstring (lines 127-128): "\`None\` means 'let xAI pick the model default' and the field is omitted from the request."
- Symptom: even with \`/verbose 2\` (which un-gates \`thinking\` events in \`chat_aggregator.should_emit_event\` at \`backend/app/core/chat_aggregator.py:66-86\`), \`deltas_from_chunk\` in \`backend/app/core/providers/_xai_stream.py:64-73\` returns \`thinking=None\` because the model didn't stream \`reasoning_content\`. No \`LLMThinkingDeltaEvent\` is yielded.

## Reproduction

1. On Telegram, set \`/verbose 2\` for a conversation pointing at an xAI reasoning model (grok-4.3).
2. Send any prompt.
3. Observe: no italic thinking block appears in chat.
4. On the web app, the same model + prompt + \`reasoning_effort=high\` shows the thinking block fine.

## Fix sketch

Thread \`reasoning_effort\` through \`ChatTurnInput\` from the Telegram bot. Options:

- **Minimal**: hardcode a default of \`"high"\` in \`bot.py\` when building \`ChatTurnInput\`. Cheapest, gets thinking back. Loses the ability to tune effort per conversation.
- **Per-conversation**: add a \`reasoning_effort\` column on \`Conversation\` (matches \`verbose_level\`), expose a \`/reasoning low|medium|high|extra-high\` slash command, fall back to a model-specific default (e.g. \`"high"\` for reasoning-capable, \`None\` for non-reasoning).
- **Inline keyboard** (preferred long-term): tie the picker UX to the same prefix-callback pattern as the verbose-toggle keyboard tracked in \`pawrrtal-oh29\`. May be a follow-up bean.

Recommend the per-conversation column + slash command for v1 because it's the same shape we already use for \`verbose_level\` and lets the keyboard work land later without schema migration.

## Todo

- [ ] Add \`reasoning_effort\` field to \`Conversation\` model + Alembic migration.
- [ ] Extend \`update_conversation_verbose_level\` pattern in \`backend/app/crud/channel.py\` with a sibling \`update_conversation_reasoning_effort\`.
- [ ] Pass through into \`ChatTurnInput\` in \`bot.py:251-272\`.
- [ ] Add \`/reasoning\` slash command in \`backend/app/integrations/telegram/handlers.py\`.
- [ ] Sensible default when unset (e.g. \`"high"\` for reasoning-capable models, \`None\` otherwise).
- [ ] Tests in \`backend/tests/test_telegram_handlers.py\` covering set/get and the default fallback.
- [ ] Verify thinking renders end-to-end on grok-4.3 via Telegram with \`/verbose 2\`.

## Related

- Pairs with \`pawrrtal-o0wq\` (newline-per-word render bug). Fixing this bug WITHOUT fixing the render bug means users will finally see thinking — and immediately notice it's broken in a different way.
- Tracking: https://github.com/OctavianTocan/Pawrrtal-AI/issues/344

---
# pawrrtal-o0wq
title: 'Telegram: thinking deltas render with a newline after every word'
status: todo
type: bug
priority: high
created_at: 2026-05-19T12:20:35Z
updated_at: 2026-05-19T12:21:50Z
---

handle_thinking() in backend/app/channels/_telegram_dispatch.py strips each delta and joins with literal \n. For delta-style providers (xAI, Gemini) that stream thinking per-token, this strips inter-token whitespace and replaces it with newlines, producing 'word\nword\nword' instead of the model's intended paragraph layout.


## Evidence

- Bug site: \`backend/app/channels/_telegram_dispatch.py:265-291\`, specifically lines 276-279:
  \`\`\`python
  chunk = str(event.get("content") or "").strip()
  if not chunk:
      return thinking_text, thinking_message_id
  thinking_text = f"{thinking_text}\n{chunk}" if thinking_text else chunk
  \`\`\`
- xAI delta shape: \`backend/app/core/providers/_xai_stream.py:64-73\` — \`deltas_from_chunk\` returns \`thinking=chunk.reasoning_content\`. xAI streams reasoning_content per chunk, often per-token. Inter-token spaces ride on individual deltas.
- Canonical pattern (no bug): \`backend/app/core/chat_aggregator.py:132-136\` does \`self.thinking += chunk\` — no strip, no \\n.
- Claude does not show this because \`_claude_events.py:185-186\` emits one event per complete thinking block (the \\n joins only between blocks, which is invisible). Gemini is delta-based and likely shows the same symptom — verify.

## Reproduction

1. On Telegram with \`/verbose 2\` (and after \`pawrrtal-6q96\` is fixed so thinking actually streams), send any prompt to grok-4.3.
2. Observe the italic thinking block rendering each word on its own line.

## Fix

\`\`\`python
chunk = str(event.get("content") or "")
if not chunk:
    return thinking_text, thinking_message_id
thinking_text = thinking_text + chunk
\`\`\`

- Drop \`.strip()\` — model is responsible for its own whitespace.
- Concatenate with no separator — mirrors the chat-aggregator contract.

## Todo

- [ ] Apply the two-line fix in \`_telegram_dispatch.py:276-279\`.
- [ ] Add a test in \`backend/tests/test_telegram_channel.py\` (or \`test_telegram_dispatch.py\` if appropriate) that drives \`handle_thinking\` with a sequence of small per-token deltas like \`["Let", " me", " think", " about", " this", "."]\` and asserts the rendered output is \`"<i>Let me think about this.</i>"\` (or whatever \`thinking_html\` produces) — NOT containing inserted newlines.
- [ ] Sanity-check Gemini thinking on Telegram with the same fix to confirm the same root cause covers both providers.

## Related

- Blocked-by-in-practice (not formally) by \`pawrrtal-6q96\`: without that fix, xAI thinking never reaches this code path on Telegram. The fix is independently correct, though, and should land regardless because Gemini is affected today.
- Tracking: https://github.com/OctavianTocan/Pawrrtal-AI/issues/345

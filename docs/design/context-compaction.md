# Design: agent context window & compaction strategy

**Status:** Proposed — needs Tavi's call on which option to ship
**Author:** Tavi + Wretch
**Last updated:** 2026-05-12

## What the agent currently sees every turn

In `backend/app/api/chat.py`:

1. **System prompt** — full content of `SOUL.md`, `AGENTS.md`,
   `USER.md`, and `PREFERENCES.md` from the user's workspace root
   (via `assemble_workspace_prompt`). Each file is capped at 64 KB.
2. **History** — the last `_HISTORY_WINDOW = 20` messages from the
   `chat_messages` table, role + content only.  Thinking text,
   tool_calls, timeline, attachments are stripped before being
   sent back to the provider.
3. **Current question** — passed separately as `question`.
4. **Tool list** — assembled per turn (see `agent_tools.py`).

That's it.  There is no summary of older messages, no semantic
recall, no embeddings, no memory mechanism.  Once a turn falls past
index 20 from the end it is **never** shown to the model again
unless the user re-pastes it.

## Why this is a problem

- **Long conversations lose continuity.**  Decisions made in
  turn 5 disappear by turn 30.  The agent contradicts itself.
- **Telegram makes it worse.**  Long-running topic threads can rack
  up hundreds of turns over days.  All of that context is lost.
- **No way to teach durable facts.**  Even when the user says "always
  call me Tavi" in turn 1, by turn 25 the model has forgotten.
  Workaround today is to write the fact into `SOUL.md` /
  `preferences.toml`, but that's manual.
- **Silent failure.**  No warning when context falls off — the
  conversation just gets worse, slowly.

## Options

### Option A — Rolling summary (cheapest, ships first)

Maintain one `summary` column on `Conversation`.  When history
exceeds N (say 30) messages:

1. On the next turn, build a summarisation prompt over messages
   `[0..N-K]` (the oldest K-truncated chunk) plus the existing
   summary.
2. Call a cheap model (Gemini Flash) with that prompt; store the
   updated summary on `Conversation.summary`.
3. The chat request now sends `summary` as a system-prompt
   addendum + the last N-K messages as history.

**Pros:** Simple, no new infra, no embeddings.  Works on Telegram
identically to web because the summary travels with the
conversation row.

**Cons:** Summaries lose detail.  Hard to recover specific quoted
text the user references later ("what did I say about X earlier?").

**Cost:** ~1 extra LLM call per N turns.  At N=30 with Gemini Flash
that's ~0.5¢ per summary at typical token sizes.

### Option B — Vector recall (precise, more infra)

Embed every message at insert time using a local embedding model
(`embeddinggemma-300M-GGUF`, ~ours already used elsewhere).  Store
in a per-conversation pgvector table.  On each turn:

1. Embed the current question.
2. Pull top-K relevant older messages from the vector store
   (where K is small, maybe 5).
3. Prepend the top-K to history above the last-20 slice.

**Pros:** Preserves exact wording.  Surfaces relevant decisions
from far back when the topic comes up again.

**Cons:** pgvector setup, embedding service in the request path,
risk of unrelated messages getting pulled in by spurious matches.

**Cost:** Embedding latency on insert (negligible w/ a local
model), one similarity query per turn.

### Option C — Hybrid (Option A + Option B together)

Summary covers the gist, vector recall pulls in exact quotes when
relevant.  Best of both worlds, most complexity.  Probably the
right end-state but not the right v1.

### Option D — Do nothing, give the agent a `read_history` tool

Add a tool that lets the agent search its own conversation history
on demand.  The agent decides when it needs older context and pays
the token cost only then.

**Pros:** Cheapest by default — no extra LLM call per turn.
Composable with workspace files (which the agent already searches).
**Cons:** Relies on the agent realising it needs older context,
which it often won't.

## Recommendation

**Ship Option A first.**  It's the smallest scope, the only one
that requires zero new infra, and it materially improves long-form
quality immediately.  Add Option B later if specific-quote recall
becomes a real problem.  Option D is a nice-to-have that can layer
on top of either.

### Option A — concrete plan

1. New column: `Conversation.summary: Text | null`,
   `Conversation.summary_updated_through_ordinal: int | null`
   (so we know how much history is already covered).
2. New module: `backend/app/core/conversation_summary.py` —
   `maybe_update_summary(session, conversation_id) -> None` that
   decides whether to run, builds the prompt, calls the model,
   writes back.
3. Trigger in `chat.py`:  fire-and-forget (`asyncio.create_task`)
   after the assistant stream completes, gated by
   `len(history) >= 30 and (summary_updated_through_ordinal or 0) <
   len(history) - 10`.
4. System prompt assembly: when `summary` is present, append it as
   an `## Earlier in this conversation` section after AGENTS.md.
5. Telegram works automatically because both surfaces share
   `chat_messages` + the same `Conversation` row.
6. Cost guard: skip summarisation if the conversation is on a
   premium model (charge the summary against Gemini Flash always).

### What we DON'T do here

- We don't compact `SOUL.md` / `AGENTS.md` / `preferences.toml`.
  Those are workspace files; the user owns them.
- We don't auto-prune `chat_messages` — disk is cheap, the table
  is already the rehydration source for the UI.
- We don't summarise tool-call payloads — keep `tool_calls` and
  `timeline` fields out of the summarisation input because they're
  noisy and rarely matter for continuity.

## Open questions (Tavi to answer)

1. **N (window) and K (summarisation chunk):**  20 and 10?  30 and 10?
2. **Which model for the summary?**  Gemini Flash by default OK?
3. **Should the user see the summary?**  Suggest yes — a collapsed
   panel in the chat UI labeled "Earlier" so it's auditable.
4. **What about a hard kill — wipe + restart from summary only?**
   When a conversation crosses, say, 200 messages, do we collapse
   everything before the last 20 into the summary and forget the
   raw messages from the provider's POV?  (We'd keep the DB rows
   for the UI.)

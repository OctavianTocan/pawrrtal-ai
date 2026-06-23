# Contract 1 — Message Parts

**Purpose**: One ordered, complete, lossless array IS the message. Every model/CLI output normalizes to it; every client (web/Telegram/CLI/mobile) renders it identically. Replaces the four overlapping shapes today: `LLMEvent` (`agents/types.py:101`), `AgentEvent` (`types.py:171`), `StreamEvent` (`providers/base.py:25`), and the lossy persisted `timeline` quad (`aggregator.py:213`, `frontend/lib/types.ts:58`).

## Shape

`Message = { id, conversation_id, role: user|assistant|tool, parts: Part[], status, usage?, created_at }`

`parts[]` is **order-significant and complete** — assistant text and tool calls interleave in true arrival order. (Today's `timeline` only holds `{kind:'thinking'}`/`{kind:'tool'}` and pushes text/error into sibling fields, so the interleave is lost; this fixes that.)

**Part** — discriminated union on `type`:

| type | fields | evolves from |
|---|---|---|
| `text` | `{ text }` | StreamEvent `delta` / `LLMTextDeltaEvent` / `aggregator.content` |
| `reasoning` | `{ text, block_index?, summary? }` | StreamEvent `thinking` (block_index `base.py:42`, summary `base.py:79`); timeline `{kind:'thinking'}` |
| `tool_call` | `{ tool_call_id, name, input, display? }` | StreamEvent `tool_use` / `ToolCallContent`; timeline `{kind:'tool'}` |
| `tool_result` | `{ tool_call_id, output, is_error }` | StreamEvent `tool_result` (+`is_error` `base.py:53`) |
| `tool_progress` | `{ tool_call_id, output, transient }` | StreamEvent `tool_progress` (ephemeral; may not persist) |
| `error` | `{ message, error_code? }` | StreamEvent `error` (+`error_code` `base.py:58`) |
| `artifact` | `{ kind, data, provider }` | StreamEvent `artifact` (`base.py:84`) |
| `image` | `{ data, media_type }` | `stream()` images kwarg (`base.py:144`); inbound user parts |

- Every `tool_call` has a **status lifecycle**: `pending → running → completed | errored` (today `_ToolCall.status`, `aggregator.py:38`). A `tool_result`/`tool_progress` patches its matching `tool_call` by `tool_call_id`.
- **Usage is NOT a part** — it is message-level `{ input_tokens, output_tokens, cost_usd, total_input_tokens?, total_output_tokens? }` folded once per turn (`aggregator.py:176`).

## Transport — PartDelta

A `PartDelta` stream mutates the array: `{ op: append_part | patch_part | append_text, part_index?, tool_call_id?, value }`. The current `StreamEvent` dict is the **wire encoding** of a PartDelta; the channel projects PartDelta→SSE exactly as today (`sse.py:42` — `data: {json}\n\n` + `[DONE]`).

**Content vs control**: control signals (session created, transient progress, `[DONE]`) ride a **separate envelope field**, never inside `parts[]` — see [gateway.md](./gateway.md).

## Invariant

Folding the full PartDelta stream **server-side** (aggregator) and **client-side** (reducer) MUST yield byte-identical `parts[]`. This is the existing live-vs-rehydrated guarantee (`aggregator.py:1-9`) made **structural** instead of hand-maintained byte-for-byte between `aggregator.py` and `chat-reducer.ts`.

## Open

- Backfill: upcast legacy `{content,thinking,tool_calls,timeline}` rows to `parts[]`, or synthesize `parts[]` on read.
- Are `tool_progress`/`transient` first-class parts, ephemeral patches, or a control channel? (Today `transient:true`, forwarded but not persisted.)
- Multimodal: inbound images = user-message parts; outbound artifacts = assistant parts; is artifact `data` opaque-by-provider or normalized?

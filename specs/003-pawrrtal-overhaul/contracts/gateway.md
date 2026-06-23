# Contract 4 — Gateway: internal parts model + external OpenAI/Anthropic façade

**Purpose**: Two faces of one model. **Internal**: the PartDelta stream + control envelope ([message-parts.md](./message-parts.md)). **External**: an OpenAI/Anthropic-compatible HTTP surface that **projects** the internal stream, reusing the channel `deliver` seam (`channels/base.py:113`, `sse.py`) — so third parties can drive Pawrrtal as if it were a model. **No external/third-party AI gateway is in this path** (self-hosted decision Q1).

## Internal envelope (host → channel)

A frame is either:

- `{ content: PartDelta }` — mutates `parts[]` (Contract 1).
- `{ control: SessionSignal | TransientProgress | Done }` — **never enters `parts[]`**:
  - `SessionSignal = { kind: provider_session_created, provider, session_id }` (today StreamEvent `type='internal'`, `runner.py:281`).
  - `TransientProgress = { stage, text }` (today StreamEvent `transient:true` + `stage`, `runner.py:257`).
  - `Done` = end-of-turn sentinel (today `data: [DONE]\n\n`, `sse.py:47`).

The existing `StreamEvent` dict IS this envelope flattened; the contract just names the content-vs-control split the runner already special-cases.

## External façade (third parties drive Pawrrtal)

- **Request**: OpenAI `chat/completions` OR Anthropic `messages` shape → normalized to an inbound user `Message{parts:[text|image]}` + `model_id` (parse via `providers/model_id.py`) + tools. Mirrors `ChannelMessage` normalization (`channels/base.py:45`).
- **Response**: project the internal PartDelta stream to the requested dialect:
  - **OpenAI**: `text`→`choices[].delta.content`; `tool_call`→`delta.tool_calls[]`; `reasoning`→`reasoning_content`; `usage`→`usage`; `Done`→`data:[DONE]`.
  - **Anthropic**: `text`→`content_block_delta(text)`; `reasoning`→thinking block; `tool_call`→`content_block(tool_use)`; `tool_result`→`tool_result`; `usage`→`message_delta.usage`.
- This is the **inverse** of what claude_code_pty/opencode_go already *consume* (they use `AsyncOpenAI` against `ccpty serve`) — Pawrrtal becomes the server those clients speak to.

## Rules

- The external façade is a **pure projection** of `parts[]` — it adds NO new content kinds and is never the source of truth.
- Control-plane frames (SessionSignal, TransientProgress) are **not exposed externally** unless the dialect has a slot; `Done` maps to the dialect terminator.
- `tool_enforcement` from the manifest ([provider-taxonomy.md](./provider-taxonomy.md)) governs whether external tool calls are gated or passed through; a `none` provider MUST **reject** external tool requests rather than silently drop them (the agy_cli failure mode).
- **Providers stay native** behind the gateway — CLI/PTY providers are driven directly under `providers/<provider>/`, never proxied through a third-party gateway.

## Open

- Which dialect is the **v1** façade — OpenAI (what ccpty/opencode_go speak) or Anthropic (cleaner map from internal parts)? Possibly OpenAI first, Anthropic as a follow-up story.
- Gateway auth/tenancy: does the façade expose Pawrrtal's own auth or proxy the underlying provider's credentials, and how does that interact with the session `context_owner`?

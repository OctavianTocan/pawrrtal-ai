# Design: OpenAI Codex OAuth provider for GPT text models

**Status:** Live for text models via the vendored `openai_codex` SDK 0.131.0a4 + matching `openai-codex-cli-bin==0.131.0a4` wheel (upstream's Python SDK has not been re-versioned past 0.131.0a4 even though the Rust/CLI side has reached 0.134.0 — pin both together; tracked in a follow-up bean). Approvals deny-all (see bean `pawrrtal-roi0` for the tool bridge that will replace it). Per-workspace OAuth override not yet wired (bean `pawrrtal-nf6y`).
**Author:** Tavi + Wretch
**Last updated:** 2026-05-12

## Summary

We already authenticate to the Codex backend for image generation
(`backend/app/core/tools/image_gen.py`).  The same auth token, same
endpoint, and same Responses API protocol also serve text completions.

This doc is the **canonical reference** for adding text-model support.
It's built from a deep read of:

- OpenAI Codex docs (`developers.openai.com/codex`)
- The official Codex CLI Rust source
  (`github.com/openai/codex/codex-rs`)
- Multiple independent OAuth-based Codex clients
  (`EvanZhouDev/openai-oauth`, `oauth-codex`, `codex-auth`,
  `codex-open-client`, `codex-backend-sdk`)
- OpenCode plugins
  (`pproenca/opencode-openai-codex-auth`,
  `ndycode/oc-codex-multi-auth`,
  `withakay/opencode-codex-provider`)
- The Roo-Code provider
  (`RooCodeInc/Roo-Code/src/api/providers/openai-codex.ts`)
- `badlogic/pi-mono` issue #3579 (header gateway compatibility)
- Reported failures: openai/codex#11743, openai/codex#14743,
  openai/codex#15502, openclaw/openclaw#64133

If any section conflicts with the live Codex CLI behaviour, **the CLI
wins** — these endpoints are private to OpenAI and the wire shape can
change without notice.

## Why use Codex OAuth instead of an API key

- ChatGPT Plus/Pro subscription pricing beats per-token API key
  pricing at our usage shape.
- Users (Tavi + Esther) already have Codex OAuth configured for
  image generation; reusing it is one less secret to manage.
- Fast-mode + reasoning summaries are gated on subscription auth.
- `api.openai.com/v1/responses` **rejects** ChatGPT OAuth tokens
  with `401 Missing scope api.responses.write` — the Codex sub-path
  bypasses this gate.  That's the entire reason this provider exists.

## Confirmed endpoint + transport

| Property        | Value                                                |
| --------------- | ---------------------------------------------------- |
| Endpoint        | `https://chatgpt.com/backend-api/codex/responses`    |
| Method          | `POST`                                               |
| Streaming       | **Required.**  `stream: true` in body, `Accept: text/event-stream` header.  Non-streaming returns 400. |
| Storage         | **`store: false` required.**  `store: true` returns `400 Store must be set to false`. |
| `previous_response_id` | Not supported (depends on storage).  Multi-turn uses stateless `reasoning.encrypted_content` instead. |
| Max body size   | ~4 MB (proxy default in `openprx`).                  |
| Stream idle timeout | 45 s default, 180 s upper bound observed.         |

## Auth flow

### `~/.codex/auth.json` schema

The Codex CLI writes this file on login.  Our code reads from the same
file (already done in `image_gen.py`).  Schema:

```json
{
  "OPENAI_API_KEY": null,
  "auth_mode": "chatgpt",
  "email": "user@example.com",
  "tokens": {
    "id_token": "eyJ...",
    "access_token": "eyJ...",
    "refresh_token": "...",
    "account_id": "org-..."
  },
  "last_refresh": "2026-05-12T14:00:00.000Z"
}
```

`OPENAI_API_KEY` is non-null **only** when the user signed in with an
API key instead of ChatGPT.  When it's non-null, skip the OAuth flow
entirely — `tokens` will be absent and the access path is a normal
`api.openai.com/v1` request with that key as bearer.

### OAuth PKCE flow (for our own login)

If we want to support sign-in from inside Pawrrtal (vs. requiring the
user to run the Codex CLI first):

| Property        | Value                                                |
| --------------- | ---------------------------------------------------- |
| Client ID       | `app_EMoamEEZ73f0CkXaXp7hrann`                       |
| Issuer          | `https://auth.openai.com`                            |
| Token URL       | `https://auth.openai.com/oauth/token`                |
| Authorize URL   | `https://auth.openai.com/oauth/authorize`            |
| Scopes          | `openid profile email`                               |
| Callback        | `http://localhost:1455/auth/callback`                |
| PKCE            | S256                                                 |
| Device code     | Supported (`POST /oauth/device/code`)                |

**Note:** port `1455` is hardcoded by the official CLI.  If the Codex
CLI is running during our login flow it will steal the callback.
Tell users to quit it during first auth.

### Refresh

`POST https://auth.openai.com/oauth/token` with:

```json
{
  "grant_type": "refresh_token",
  "refresh_token": "<from auth.json>",
  "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
  "scope": "openid profile email"
}
```

Response includes a new `access_token`, optionally a new `id_token`,
and **optionally a new `refresh_token`** (rotate it if present).

**🚨 Critical gotcha:** Refresh tokens are **single-use**.  If two
processes (e.g. the Codex CLI and our backend) both try to refresh at
the same time, one wins and the other invalidates.  See
openai/codex#15502.  Mitigations:

1. Centralise refresh through one async lock per host process.
2. After 401 on a stream, re-read `auth.json` from disk (the CLI
   might have refreshed it concurrently) and retry once before
   running our own refresh.

### Extracting `chatgpt_account_id`

Two paths:

1. **Cheap:** read `tokens.account_id` from `auth.json` directly.
2. **Fallback:** decode the JWT `id_token` (base64url payload) and
   read `claims["https://api.openai.com/auth"].chatgpt_account_id`.

Both should produce the same value; use (1) and fall back to (2)
when the field is missing in older auth files.

## Required request headers

This is the **exact** header set our provider must send.  Validated
against three independent reference implementations.

```http
POST /backend-api/codex/responses HTTP/1.1
Host: chatgpt.com
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <access_token>
OpenAI-Beta: responses=experimental
chatgpt-account-id: <account_id>
originator: pawrrtal
session_id: <uuid v4 per request>
```

Optional but recommended:
- `x-client-request-id: <our conversation_id>` — for log correlation.

**Header gotchas:**

- **`session_id` (with underscore)** is what the backend keys
  cache-affinity on.  `pi-mono#3579` shows strict HTTP gateways
  reject underscore headers — irrelevant here because we hit
  `chatgpt.com` directly, but worth knowing if we ever proxy through
  one.
- **`originator`** is critical.  If you set it to `codex_cli_rs`,
  the backend enters **strict mode**: it validates that the
  `instructions` text exactly matches the Codex CLI's `prompt.md`
  AND that the `tools` list is exactly `shell` + `update_plan` with
  exact schemas, AND that the model is `gpt-5`.  Anything else
  returns `400 {"detail": "Instructions are not valid"}`.  We do
  **not** want strict mode — use our own originator string
  (`pawrrtal`, `pawrrtal/0.1.0`, or whatever).  Strict mode is only
  for clients that want to impersonate the official CLI.
- **Do not send `temperature`** — `400 Unsupported parameter:
  temperature`.
- **Do not send `User-Agent`** is sometimes reported as problematic
  but `RooCodeInc/Roo-Code` happily sends a `User-Agent` with their
  own product/version string and that works.  Probably safe; skip if
  in doubt.
- **`OpenAI-Beta: responses=experimental`** — required.  Without it
  the endpoint may default to an older shape.

## Request payload

```json
{
  "model": "gpt-5",
  "instructions": "You are Pawrrtal's assistant. ...",
  "input": [
    {
      "type": "message",
      "role": "user",
      "content": [
        {"type": "input_text", "text": "What's 2 + 2?"}
      ]
    }
  ],
  "tools": [],
  "tool_choice": "auto",
  "reasoning": {
    "effort": "medium",
    "summary": "auto"
  },
  "text": {"verbosity": "medium"},
  "include": ["reasoning.encrypted_content"],
  "stream": true,
  "store": false
}
```

### Rules

- **`model`** — known-good values: `gpt-5`, `gpt-5-codex`, `gpt-5.4`,
  `gpt-5.5`, `gpt-5-mini`, `gpt-5-nano`.  Subscription tier determines
  which models the user can actually access; unknowns return
  `400 Unsupported model`.  Plan to call `GET
  /backend-api/codex/models` (when available) or hardcode + let the
  backend reject.
- **`instructions`** — system prompt at the top level (NOT inside
  `input`).  Free-form string when `originator` is your own value.
- **`input`** — Responses API format (NOT chat completions
  `messages`).  Each item is `{type: "message", role,
  content: [{type: "input_text", text}]}` OR
  `{type: "reasoning", encrypted_content, ...}` (for multi-turn
  state).  Roles allowed: `user`, `assistant`, `system`,
  `developer`.
- **`stream: true`** — required.  Backend rejects `false`.
- **`store: false`** — required.  Backend rejects `true`.
- **`reasoning.effort`** — `minimal | low | medium | high`.
  `gpt-5-codex` rejects `minimal` (silently normalised to `low` by
  some clients).
- **`reasoning.summary`** — `auto | detailed`.
- **`text.verbosity`** — `low | medium | high`.  `gpt-5-codex` only
  accepts `medium`.
- **`include: ["reasoning.encrypted_content"]`** — required for
  multi-turn statelessness (see below).
- **Forbidden:** `temperature`, `max_output_tokens`,
  `max_completion_tokens`, `previous_response_id`, `messages`,
  `background`.

### Tool format (when sending tools)

Responses API tools are flat — properties at the top level, NOT
nested under `function`:

```json
{
  "type": "function",
  "name": "render_artifact",
  "description": "...",
  "parameters": {
    "type": "object",
    "properties": { ... },
    "required": [ ... ]
  },
  "strict": true
}
```

Our existing Claude/Gemini tool schemas are easy to translate to this.

## Stream event handling

Server-sent events.  Each event is `event: <type>` + `data: <json>`.
Key types we care about:

| Event type                              | Meaning                                                     |
| --------------------------------------- | ----------------------------------------------------------- |
| `response.created`                      | Request accepted.  Capture `response.id`.                   |
| `response.output_text.delta`            | Text token chunk.  `data.delta` is the new fragment.        |
| `response.output_text.done`             | Text item finished.                                         |
| `response.reasoning_summary.delta`      | Reasoning summary text chunk (visible "thinking").          |
| `response.reasoning_text.delta`         | Raw reasoning text (when enabled).                          |
| `response.output_item.added`            | A new item started — could be `function_call`, `message`, `reasoning`, etc.  |
| `response.function_call_arguments.delta` | Streamed JSON for a function call's `arguments`.          |
| `response.function_call_arguments.done` | Function call args complete; can dispatch the call.         |
| `response.output_item.done`             | Item closed — full content available in `data.item`.        |
| `response.completed`                    | Full response finished.  `data.response.output` has the full item list including reasoning items with `encrypted_content`.  |
| `error`                                 | Stream-level error.                                         |
| `[DONE]`                                | Plain SSE terminator after `response.completed`.            |

Map to our `StreamEvent` union:

| Codex event                        | Our `StreamEvent`                                 |
| ---------------------------------- | ------------------------------------------------- |
| `response.output_text.delta`       | `{type: "delta", content: <delta>}`               |
| `response.reasoning_summary.delta` | `{type: "thinking", content: <delta>}`            |
| `response.output_item.added` (function_call) | `{type: "tool_use", name, input: {}, tool_use_id}` (input filled as deltas arrive)  |
| `response.function_call_arguments.delta` | append to that tool_use's `input` JSON buffer |
| `response.function_call_arguments.done`  | emit final `tool_use` with parsed input       |
| error                              | `{type: "error", content: <error.message>}`       |
| `response.completed`               | end of stream                                     |

Tool **results** are not part of the same response.  After the
backend yields a `function_call`, the loop owner (us) executes the
tool, then sends the next request with the call output appended to
`input`:

```json
{
  "type": "function_call_output",
  "call_id": "<id from function_call>",
  "output": "<stringified result>"
}
```

This pattern is already how our Claude and Gemini loops work; the
codex provider just speaks Responses-shaped items instead of
Anthropic/Gemini-shaped tool messages.

## Multi-turn statelessness

Since `store: false` is mandatory and `previous_response_id` is
rejected, we manage conversation state by sending the entire turn
history as `input` items every request.  Standard for our codebase
(we already do this for Claude + Gemini, capped at 20 messages by
`_HISTORY_WINDOW`).

**The Codex-specific wrinkle:** reasoning models compute internal
state that's expensive to recompute.  The Responses API exposes this
as opaque `reasoning` items with an `encrypted_content` blob —
include them verbatim in subsequent `input` arrays and the model
picks up where it left off without redoing reasoning.

### How to use it

1. Send `include: ["reasoning.encrypted_content"]` on every request.
2. On the `response.completed` event, grab every item with
   `type: "reasoning"` from `data.response.output`.
3. On the next turn, before the new user message in `input`, append:
   - the assistant `message` items from the previous turn (so the
     model sees what it actually said)
   - the `reasoning` items verbatim (with their `encrypted_content`)
   - any `function_call` + `function_call_output` items for tools
     that ran

Order matters: items must appear in the same sequence the model
produced them.  Skip items at your peril — partial reasoning state
can confuse the model.

## Implementation plan (code-level)

### 1. Lift the auth helper

`backend/app/core/codex_auth.py` (new):

```python
"""Codex OAuth token resolution shared by image_gen + text provider."""

import json
import os
import time
from pathlib import Path

import httpx

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"


def resolve_codex_auth(override: str | None = None) -> tuple[str, str]:
    """Return (access_token, account_id).

    Resolution order:
      1. `OPENAI_CODEX_OAUTH_TOKEN` override (no account_id available).
      2. `$CODEX_HOME/auth.json` (default `~/.codex/auth.json`).

    Raises RuntimeError when no auth is configured.
    """
    if override:
        return (override, _decode_account_id_from_jwt(override))

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    auth_file = codex_home / "auth.json"
    if not auth_file.exists():
        raise RuntimeError("No Codex auth.  Run `codex login` or set OPENAI_CODEX_OAUTH_TOKEN.")

    data = json.loads(auth_file.read_text())
    tokens = data.get("tokens") or {}
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id") or _decode_account_id_from_jwt(
        tokens.get("id_token") or access_token
    )
    if not access_token or not account_id:
        raise RuntimeError("auth.json is missing tokens.access_token or account_id.")
    return (access_token, account_id)


async def refresh_codex_token() -> None:
    """Refresh the access token.  Single-use refresh token — see #15502."""
    # Reads auth.json, POSTs to TOKEN_URL, writes back.  Use an asyncio.Lock
    # at module scope to serialise refresh attempts in this process.
    ...
```

### 2. New provider

`backend/app/core/providers/openai_codex_provider.py`:

```python
class OpenAICodexProvider(LLMProvider):
    """Streams via chatgpt.com/backend-api/codex/responses."""

    async def stream(self, question, conversation_id, user_id, *,
                     history, tools, system_prompt) -> AsyncIterator[StreamEvent]:
        access_token, account_id = resolve_codex_auth(
            override=os.environ.get("OPENAI_CODEX_OAUTH_TOKEN"),
        )

        body = self._build_request(question, history, tools, system_prompt)
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {access_token}",
            "OpenAI-Beta": "responses=experimental",
            "chatgpt-account-id": account_id,
            "originator": "pawrrtal",
            "session_id": str(uuid.uuid4()),
            "x-client-request-id": str(conversation_id),
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", CODEX_RESPONSES_URL,
                                     json=body, headers=headers) as response:
                if response.status_code == 401:
                    # Try one refresh + retry before giving up.
                    await refresh_codex_token()
                    # ... retry ...
                response.raise_for_status()
                async for event in self._parse_sse(response):
                    yield event
```

`_build_request` and `_parse_sse` follow the contracts above.

### 3. Factory wiring

`backend/app/core/providers/factory.py`:

```python
def resolve_llm(model_id, user_id=None):
    if model_id.startswith("claude-"):
        return ClaudeProvider(model_id, user_id)
    if model_id.startswith(("gpt-", "openai-codex/")):
        return OpenAICodexProvider(model_id, user_id)
    return GeminiProvider(model_id, user_id)
```

### 4. Model catalog

Add to `/api/v1/models` so the frontend picker exposes them.
Hardcode the user-visible subset and let the backend reject anything
the user's plan doesn't include.

### 5. Tests

Replay-style, mirroring `test_claude_provider.py`:

- Recorded `response.output_text.delta` SSE stream → assert
  `StreamEvent` mapping.
- Recorded `function_call` flow → assert tool_use shape.
- 401 → refresh → retry happy path.
- 401 → refresh → still 401 → bubble error.
- Multi-turn: previous reasoning items get appended to `input` on
  turn 2.

## Concrete risks

| Risk                                          | Mitigation |
| --------------------------------------------- | ---------- |
| Endpoint deprecation (private OpenAI API).   | Wrap with the same error envelope as other providers.  Document in PR description that we depend on the Codex CLI continuing to work. |
| Refresh-token rotation conflicts (#15502).   | Single-process asyncio lock around refresh.  Re-read `auth.json` after 401 in case CLI refreshed concurrently. |
| Instructions-validation strict mode trap.    | Never use `originator: codex_cli_rs`.  Always send our own name. |
| Subscription rate limits hit mid-stream.     | Catch the specific `rate_limit_exceeded` SSE error event; surface to the user with a clear message. |
| `gpt-5-codex` rejects `minimal` effort.      | Normalise client side: if model contains `-codex` and effort is `minimal`, send `low`. |
| `gpt-5-codex` rejects `verbosity != medium`. | Same — silently normalise. |
| Refresh-token invalidated after auth.json copy.  | Doc users not to copy the file across machines.  Show clear "re-run codex login" error. |
| Stream idle timeout mid-reasoning.           | Heartbeat: every 30 s with no event, log + keep alive.  If 180 s with no event, abort and surface error. |

## Out of scope (deferred)

- API-key path: users with an `OPENAI_API_KEY` can already route
  through `api.openai.com/v1/responses`.  Add as a fallback provider
  later if asked.
- WebRTC voice calls (`/realtime/calls`) — separate concern.
- Background mode (`background: true`) — requires `store: true`,
  not supported here.

## Implementation order

1. Lift `resolve_codex_oauth_token` from `image_gen.py` to
   `core/codex_auth.py`.  Refactor `image_gen.py` to use it.  Add
   `account_id` extraction.  No behaviour change visible to users.
2. Wire the auth helper into `image_gen.py` to send the full header
   set (`session_id`, `originator: pawrrtal`,
   `chatgpt-account-id`).  This validates that header layout works
   before we touch a new provider.
3. New file: `core/providers/openai_codex_provider.py` — skeleton
   that streams a single message with no tools, maps `delta` events.
4. Add tool-call support (mirror Claude bridge).
5. Add `reasoning.encrypted_content` multi-turn support.
6. Add 401 → refresh → retry path.
7. Wire into `factory.py` with `gpt-*` and `openai-codex/*`
   prefixes.
8. Add catalog entries to `/api/v1/models`.
9. Replay-based tests.
10. Manual smoke from Tavi's account.

## References

- OpenAI Codex CLI source:
  - `codex-rs/login/src/token_data.rs` — `auth.json` schema, JWT claim parsing
  - `codex-rs/backend-client/src/client.rs` — header set, account ID handling
  - `codex-rs/codex-api/src/endpoint/responses.rs` — Responses endpoint client
- Reference implementations:
  - `github.com/EvanZhouDev/openai-oauth` — TypeScript localhost proxy
  - `github.com/pproenca/opencode-openai-codex-auth` — OpenCode plugin
  - `github.com/withakay/opencode-codex-provider` — alternative MCP-based approach
  - `github.com/RooCodeInc/Roo-Code/blob/main/src/api/providers/openai-codex.ts`
- Failure mode references:
  - `openai/codex#11743` — stream-disconnect on VPS
  - `openai/codex#14743` — wrong request body shape
  - `openai/codex#15502` — refresh-token rotation
  - `openclaw/openclaw#64133` — wrong endpoint sub-path

---

## 2026-05 Codex SDK Path (First-Class Provider + Image Plugin)

**Status (plan phase):** All implementation artifacts produced in **commented form only**.
No live code has been mutated. A later mechanical activation PR will remove the markers.

This section records the decision (per user direction) that the official
`openai_codex` Python SDK (https://github.com/openai/codex/tree/main/sdk/python)
is the desired, first-class integration path — not the reverse-engineered
Responses HTTP path documented above.

### Key Outcomes of This Plan
- New first-class provider package: `backend/app/core/providers/openai_codex/`
  - `auth.py` — unified, refresh-safe Codex OAuth resolution (lifted from image_gen + this doc)
  - `provider.py` — `OpenAICodexProvider` implementing the full native streaming contract
- Image generation via Codex agent delivered as a plugin:
  - `backend/app/plugins/openai_codex_image_gen/` (exact layout of `active_recall`)
  - Not hook-driven; invoked as a regular tool / explicit action.
- All artifacts follow the strict "commented implementation only" discipline
  (see the approved plan for the exact marker format).
- LiteLLM OpenAI routing is left 100% untouched.
- The provider must feel "butter smooth" and follow the SDK surface exactly
  ("whatever they say we should do" + "latest all the way").
- Codex "threads" are understood as persistent stateful agent sessions
  (the plan author researched the actual SDK source before writing the provider).

### Implementation Note (2026)
The Codex SDK path (first-class `openai_codex` provider + image plugin) was
implemented in phases after this document was written. The original
"commented blocks + later mechanical activation" approach was followed
initially, then activated incrementally with compatibility work against the
vendored SDK tree. The Responses-based text provider path documented above
remains as historical/secondary context.

### References Added During This Work
- Official SDK Python package and surface (primary source of truth)
- Existing image generation code + this design doc (auth reuse)
- `plugins/active_recall/` (exact structural template for the image plugin)

This completes the 2026-05 Codex SDK implementation plan.

---

## Vendored Codex Repository (as Git Submodule)

As of the integration work, the upstream `openai/codex` repository is included as a git submodule at:

```
backend/vendor/codex/
```

This gives us direct access to the official Python SDK source at:

```
backend/vendor/codex/sdk/python/
```

### Why a submodule?

- The official Python SDK (`openai_codex` package) is not (yet) a simple standalone PyPI package. It is developed inside the main Codex monorepo and expects to be installed from source (`pip install -e .` from `sdk/python`).
- Including it as a submodule makes the dependency "real" and reproducible inside the pawrrtal-ai tree, rather than requiring every developer to manually `git clone` the Codex repo.
- It allows the provider implementation and tests to reference concrete code and types from the official SDK.

### Setup for developers

After cloning pawrrtal-ai:

```bash
git submodule update --init --recursive
# Then (from backend/):
cd vendor/codex/sdk/python
uv pip install -e .
```

The test suite in `backend/tests/test_openai_codex_provider.py` automatically adds the vendored `src` directory to `sys.path` when present, enabling more realistic imports during test development.

### Pinning

The submodule is pinned to a specific commit for reproducibility. Update the pointer deliberately when we want to move to a newer Codex revision.

---

## Final Pass Status (2026-05-26)

**All major implementation artifacts have been produced in strict commented form** following the approved plan's "Implementation Discipline".

### Artifacts Delivered (All Commented)
- Full `openai_codex` provider package (`provider.py`, `auth.py`, `events.py`, `__init__.py`)
- Complete Codex-driven image generation plugin (`openai_codex_image_gen/`) modeled exactly on `active_recall`
- Expanded test skeleton
- Commented registration blocks in `model_id.py`, `factory.py`, and catalog
- Documentation updates (package README, new `docs/codex-sdk-provider.md`, root `README.md`, and this design doc)

### Verification Performed
- All Python files compile cleanly (`py_compile` passed on every new/modified file)
- New source files pass the project's 500-line hard limit
- Plugin directory structure exactly mirrors `active_recall` (non-hook-driven)
- All work remains 100% non-mutating (no live code changed)

### Remaining Manual Step
A single future PR will mechanically remove the `# === CODEX-SDK-PLAN` comment blocks and activate the feature. Because the code was written to be directly usable, that step will be low-risk and reviewable.

**Plan execution status: Complete in commented form.**

## Implementation Notes (2026-05-27)

The first-class native provider is live for text models. Key landing artefacts:

- **Provider package:** `backend/app/core/providers/openai_codex/`
  - `provider.py` — `OpenAICodexProvider` (`stream` translates SDK notifications → Pawrrtal `StreamEvent`s; installs a deny-all approval handler on the wrapped sync client before initialize)
  - `_vendor.py` — SDK import shim with opt-in `OPENAI_CODEX_ALLOW_PATH_FALLBACK` for local dev
  - `auth.py` — `OPENAI_CODEX_OAUTH_TOKEN` override resolver (per-workspace injection deferred — bean `pawrrtal-nf6y`)
  - `events.py` — `Notification` → `StreamEvent` mapper
  - `inputs.py` — history + question → `RunInput`
- **Wiring:** `backend/app/core/providers/factory.py` (lazy via `_load_openai_codex_provider_cls`), `backend/app/core/providers/model_id.py` (`Host.openai_codex`), `backend/app/core/providers/catalog/openai.py` (single row `openai-codex:openai/gpt-5.5`).
- **Persistence:** `Conversation.codex_thread_id` column + migration `027_add_codex_thread_id_to_conversations.py`; `backend/app/channels/turn_runner.py` loads/persists the thread id and listens for the provider's `codex_thread_created` internal event.
- **Submodule:** `backend/vendor/codex` pinned at upstream `rust-v0.134.0` (whose `sdk/python/pyproject.toml` reports `version = "0.131.0a4"`).
- **Tests:** `backend/tests/test_openai_codex_provider.py` (strict — auth, discovery, event mapper, provider-contract via SDK-seam mocks; image-plugin tests stay `xfail` until bean `pawrrtal-roi0`) and `backend/tests/test_openai_codex_import_isolation.py` (regression: package imports must not break other providers).

**Known follow-ups:**

- `pawrrtal-roi0` — wire `AgentTool` bridge; replace the deny-all approval handler with an agent-loop-aware one.
- `pawrrtal-nf6y` — per-workspace `OPENAI_CODEX_OAUTH_TOKEN` injection (today the token is detected but only logged).
- Bump pair to a newer upstream version when the Python SDK source moves past 0.131.0a4 — track in the deferred bean.

The previous "commented implementation only" rule from bean `pawrrtal-ujo8` no longer applies; the provider is now live in `main`-bound commits.

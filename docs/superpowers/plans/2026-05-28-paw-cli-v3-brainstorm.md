# paw CLI v3 — brainstorming doc

Date: 2026-05-28
Status: brainstorm (not yet planned; pre-eng-review)

This doc captures the design conversation around four threads the user
raised after paw v2 shipped:

1. Should `dry-python/returns` replace exceptions across the Python backend?
2. What more can `paw` do? In particular: should it own browser automation
   (Stagehand) for UI-flow E2E?
3. Should `paw` expose DB ops?
4. Does `paw` cover every provider + every user flow (web + Telegram)?

The four threads aren't equal weight. Threads 2 and 4 are the highest
leverage — they expand the surface paw can prove. Thread 1 is a posture
change with deep blast radius; thread 3 is a small targeted hatch.

---

## Thread 1 — `returns` (Result / Maybe / IOResult / FutureResult)

### What `returns` provides

After cloning `dry-python/returns@HEAD`:

- `Maybe[T]` — replaces `Optional[T]`; `.bind_optional(fn)` short-circuits on `Nothing`.
- `Result[T, E]` — replaces "raise on failure"; `.map(fn)` / `.bind(fn)` chains.
- `IO[T]` / `IOResult[T, E]` — marks impure operations.
- `Future[T]` / `FutureResult[T, E]` — async equivalents.
- `RequiresContext` — typed functional DI.
- mypy plugin enforces the railway type.

The pitch: "no more `if x is not None`, no more `try/except`, every failure path is in the type."

### Where this would help in pawrrtal backend

| Surface | Today | With `returns` |
|---|---|---|
| Provider streams | `try: yield…; except ProviderError: ...` scattered across 8 provider files | `FutureResult[Stream, ProviderError]` — one type, every provider returns it |
| MCP tool calls | broad `except Exception` in `external_mcp.py` | `IOResult[ToolOutput, McpError]` |
| LCM context assembly | `lcm_context_items` rows + optional summary fields scattered through `observe.py` | `Maybe[LCMContext]` for the assembled view |
| DB queries via `crud/*` | mix of `Optional[Row]` and "raises if not found" | `Maybe[Row]` everywhere |
| Cost / budget enforcement | bare exceptions raised inside `_chat_cost_budget.py` | `Result[ChatTurn, BudgetExceeded]` flows through the chat router |

These are real wins. The provider seam in particular has exactly the
shape `returns` is built for: many callees, one caller (the chat router),
need a uniform error type.

### Where this would hurt

- **FastAPI canon is exceptions.** `HTTPException` is the documented
  way to surface 4xx. Wrapping everything in `Result` then unwrapping
  at the route boundary adds ceremony for marginal type safety.
- **Pydantic + SQLAlchemy don't integrate.** Container values
  fall out of mypy's narrowing when you cross those boundaries; the
  adapter layer becomes a constant friction surface.
- **Coding-agent friction.** Every LLM in our session has trained on
  idiomatic `try/except` Python. Asking them to write `IOResult` chains
  produces wrong code until re-trained per-project. The recent `paw v2`
  push had 15 agents in a row produce idiomatic Python first try; any
  one of them would have stalled on a `Result` chain.
- **Performance.** Each container is a heap allocation. In the chat
  hot path (thousands of `delta` events per turn) the allocations add
  up.
- **Async ergonomics.** `FutureResult` is not as ergonomic as `async
  def` + `try/except` for the common case. The wins of railway show
  up when you have 5+ steps in a chain; most of our async code is 1–3
  steps.

### Recommended posture

**Don't blanket-adopt.** Use the existing exception narrowing rule
(`.claude/rules/clean-code/python-logging-exceptions.md`) — that's
where 80% of the safety win lives without paying the ceremony cost.

**Do consider it for one or two surgical surfaces** where the railway
pattern shines:

1. **Provider abstraction layer** (`backend/app/core/providers/`).
   Each provider's `stream()` could return `FutureResult[Stream,
   ProviderError]` so the chat router orchestrates failover, retry,
   and fallback declaratively. This is the textbook fit.
2. **`backend/app/crud/`** — already `Optional`-heavy. Migrating to
   `Maybe[Row]` is a mechanical sweep with a clear type win.

These two surfaces could be migrated incrementally (one provider
per PR, one CRUD module per PR) without forcing the whole codebase to
swap idioms. After 4–6 weeks of living with it on those surfaces,
re-evaluate. If the team likes it, expand; if not, the blast radius
of reverting is bounded.

**Don't migrate**: API routes, settings/config, voice/transcriber,
schedulers, anything that lives downstream of pydantic.

**Decision needed before starting**: do we want the mypy plugin
strictness on the whole codebase, or scoped via `mypy.ini` overrides?
The plugin's strictness flags will fire on every file once enabled.

### Open question for the user

**"Pilot returns on the provider seam only, for 4 weeks, then
re-evaluate?"** is the proposal. If yes, the first bean is
`refactor(providers): adopt returns FutureResult on the provider
seam` and it should land in isolation before anything else changes.

---

## Thread 2 — More CLI: browser automation via Stagehand

### The case

Right now `paw verify chat-roundtrip` proves the HTTP layer works.
It cannot catch:

- **Hydration faults** — React 19 promotes some hydration warnings to
  fatal errors. paw is blind to these because they only fire in a
  real browser.
- **Race conditions on first render** — the `LoginForm` →
  `window.location.replace('/')` workaround documented in the workspace
  facts memo exists *because* `router.push` lost the cookie race. paw
  can't see that race; only a browser can.
- **Visual regressions** — sidebar creep, scrim opacity, motion drift.
- **TanStack Router auth gates** — paw uses cookies directly, doesn't
  exercise the `beforeLoad` guards.
- **Onboarding flows** — UI-level state machines that don't surface in
  the API.

Stagehand (https://docs.stagehand.dev/llms.txt) is a Playwright wrapper
with LLM-driven verbs (`.act("click the new chat button")`,
`.extract("the model in the model selector")`). It's the natural seam:
keep paw's HTTP layer fast and deterministic, layer a UI verb on top
that's slower but proves render-correctness.

### Three concrete proposals

#### Proposal A — `paw ui <verb>` as a new top-level subcommand group

```
paw ui login --as @dev-admin       # Stagehand sign-in
paw ui send "hello" --new          # drives the React chat composer
paw ui open conversation <id>      # navigates + asserts the URL/sidebar
paw ui screenshot --to FILE        # capture for visual diffing
paw ui assert-no-console-errors    # smoke that the page didn't throw
paw ui verify chat-roundtrip       # full UI variant of the HTTP scenario
```

Sits under `backend/app/cli/paw/commands/ui.py` + a new `paw/ui/`
subpackage for the Stagehand client wrapper.

#### Proposal B — Two-layer assertion mode in existing verify suites

Add `--layer http|ui|both` to existing verify suites:

```
paw verify chat-roundtrip --layer both --model litellm:openai/gpt-4o-mini
```

`--layer http` is today's behaviour. `--layer ui` re-runs the same
scenario through Stagehand and asserts the rendered DOM. `--layer
both` runs both and diffs.

This is the *dream* mode. Whatever HTTP-layer scenarios we already
trust get a free UI counterpart with one flag.

#### Proposal C — `paw ui dogfood` for exploratory bug-hunts

```
paw ui dogfood --duration 2m --model litellm:openai/gpt-4o-mini
```

Drives the UI semi-autonomously: click around, fill forms, watch for
console errors / 5xx / unresponsive renders. Outputs an annotated
trace.

### Recommended path

Land **A first** as scaffold (Stagehand client wrapper + `paw ui
login` + `paw ui send`), then **B** as the highest-value extension
(`--layer ui` on the existing chat-roundtrip + telegram suites).
**C** can be a v4 experiment.

### Risks

- **Stagehand depends on an LLM for natural-language verbs.** Adds
  cost + non-determinism to verify runs. Mitigations: pin the model,
  cache its DOM-action plans by verb signature, prefer explicit
  selectors when possible.
- **Browser dependency.** Adds Playwright + a headless Chrome to the
  paw install footprint. Acceptable since the use case is dev-loop +
  CI, not user-facing.
- **Stagehand version drift.** Lock to a specific version, vendor docs.

### Open question for the user

**"Is the user willing to spend the LLM-call cost for `--layer ui`
runs in CI?"** Each `paw verify <suite> --layer both` adds N
LLM-decided UI actions × cost-per-decision. Probably fine for the
self-hosted runner but worth flagging.

---

## Thread 3 — DB ops in `paw`

### Today

Zero. paw goes through the API exclusively. The only "DB-flavoured"
verb is `paw lcm context <conv-id>` which still hits an API endpoint.

### Cases where DB ops would unblock work

1. **Verify scenario fixtures.** `paw verify cost-and-budget` would
   benefit from seeding "user has $5 of usage already" without
   driving a real chat first.
2. **Repro reduction.** A bug report like "the sidebar broke when
   I had 50 conversations" — `paw db seed conversations --count 50`
   should reproduce the shape without 50 chat turns.
3. **Cleanup.** `paw db reset --persona-only --yes` to nuke a
   persona's rows without touching the DB schema.
4. **Debug.** `paw db inspect ledger --conversation <id>` to see what
   actually got persisted vs what the frontend received.

### What NOT to do

- **No raw `paw db query SQL`.** Lets the CLI silently corrupt
  invariants. Verify scenarios become tightly coupled to schema; the
  next migration breaks the test fixture. Just don't.
- **No `paw db migrate up/down`.** That's alembic's job. paw should
  call `alembic upgrade head` (it already could, via subprocess) but
  shouldn't own migration semantics.

### Recommended path

Add a **narrow** `paw db` subgroup backed by typed Python helpers,
not raw SQL:

```
paw db seed conversations --count N [--workspace ID]
paw db seed memories --kind FACT --content "..."
paw db inspect ledger --conversation ID [--limit N]
paw db inspect lcm --conversation ID
paw db reset --persona-only --yes
paw db migrations status         # just shells alembic
```

Implementation: import the same `crud/*` helpers the API uses; never
talk to the DB directly via SQLAlchemy text. That keeps verify
fixtures coupled to the same invariants the production code enforces.

`paw db seed` is the load-bearing verb here — it would unblock
`pawrrtal-7uo7` (verify lcm-active-recall) by letting us seed memories
without needing a backend HTTP endpoint to exist first. It also makes
`pawrrtal-x9u4` (the bean tracking the missing LCM HTTP surface) less
urgent — if paw can seed at the CRUD layer, the verify scenarios
don't strictly need new HTTP endpoints, only the production code
needs them.

### Open question for the user

**"Is shipping `paw db seed` (calls crud helpers directly) instead of
`pawrrtal-x9u4` (full HTTP surface) an acceptable shortcut?"** It
buys 80% of the test value at 20% of the effort; the cost is that
the verify scenarios use a different path than the production code.

---

## Thread 4 — Provider + UI + Telegram coverage audit

### Providers shipped

```
backend/app/core/providers/
  agy_cli         (Agentic CLI provider)
  catalog         (catalog metadata, not a runtime provider)
  claude          (Anthropic)
  gemini          (Gemini API)
  gemini_cli      (Gemini CLI subprocess)
  openai_codex    (Codex SDK)
  opencode_go     (OpenCode Go subprocess)
  xai             (Grok)
  + litellm_provider.py (LiteLLM wrapper for ~everything else)
```

### Current verify coverage

| Provider | Direct verify? | Indirect via `chat-roundtrip`? |
|---|---|---|
| openai_codex | ✅ (`verify codex`) | ✅ |
| litellm-wrapped (openai gpt-*, anthropic, etc.) | — | ✅ (default `chat-roundtrip` model) |
| claude (native) | ❌ | only if `--model` chosen |
| gemini | ❌ | only if `--model` chosen |
| gemini_cli | ❌ | only if `--model` chosen |
| xai | ❌ | only if `--model` chosen |
| opencode_go | ❌ | only if `--model` chosen |
| agy_cli | ❌ | only if `--model` chosen |

**Gap:** every non-Codex provider only gets tested if `verify
chat-roundtrip` is run with `--model` pointing at it. There's no
suite that says "for every shipped provider, run the same scenario."

**Recommended:** add `paw verify all-providers` that iterates over the
catalog, picks one model per provider, runs `chat-roundtrip` for
each. Surfaces broken providers in CI in one job instead of N
human-chosen models.

### Telegram coverage

| Capability | paw can drive it? |
|---|---|
| Link a Telegram account | ✅ (`verify telegram` + `paw channels link telegram`) |
| Unlink | ✅ |
| Send a message TO the bot (i.e. receive an update on the backend) | ❌ — `POST /api/v1/channels/{provider}/simulate` doesn't exist |
| Bot replies (delivery side) | ❌ — paw never exercises the outbound bot delivery path |
| Voice memo from Telegram | ❌ — STT not paw-exposed |

**Bigger gap:** the Telegram channel is currently a *receive-only*
test surface from paw's POV. We can prove link-codes get issued; we
cannot prove that a real Telegram update flows through the same chat
pipeline.

**Recommended (file as bean):**

1. Backend: add `POST /api/v1/channels/telegram/simulate` that
   accepts a synthetic Telegram update (text + reply-to + chat-id)
   and pushes it through the same handler the real webhook uses.
   Gated on `settings.telegram_simulate_enabled` (dev-only).
2. paw: `paw channels simulate-update --text "hello"` posts to it.
3. paw verify: extend `verify telegram` with the simulate path so the
   full link → message → reply → DB-row chain is asserted.

### Web app feature coverage

Things a user can do in the web app that paw currently can't:

- **Login UI flow** — paw uses dev-admin via cookie, not the form.
- **Workspace switcher UI** — backend works, UI selection doesn't.
- **Sidebar conversation operations** — rename, delete (paw can drive
  these via API, but the UI-state-machine interactions like
  multi-select are blind).
- **Settings sections** — personalization, appearance, billing,
  integrations. paw covers some via API (workspace env), nothing via
  UI.
- **Chat UI rendering** — markdown, code blocks, thinking accordions,
  tool-call cards, embedded plots. paw asserts on `final_text` but
  not on the structured rendering.
- **Onboarding** — first-time UX with empty workspace.
- **Telegram link UI** — paw drives the API, not the UI flow that
  shows the QR code.

**Every item above is an argument for Thread 2 (Stagehand).** Without
a UI layer, paw will keep being half-blind to the user's experience.

### Other API surfaces with no verify coverage

From `backend/app/api/`:

- `exports.py` — bulk export of conversations. No paw verify.
- `personalization.py` — user-level prefs. No paw verify.
- `completions.py` — non-streaming completions endpoint. No paw verify.
- `stt.py` — speech-to-text. Not in paw at all.
- `appearance.py` — frontend-only theme prefs. Less important.
- `projects.py` — projects feature. No paw verify.
- `mcp_servers.py` — CRUD covered (`paw mcp`); no end-to-end "MCP
  tool gets invoked during chat" verify suite.

**Recommended (file as follow-up beans):**

- `paw verify mcp-tool-roundtrip` — register an MCP server, send a
  chat turn that should invoke it, assert tool-result events flow
  through the SSE stream.
- `paw verify exports-roundtrip` — create a conversation, export it,
  diff the export against the source.
- `paw verify stt-roundtrip` — upload a short audio file, assert the
  transcript lands.

---

## Summary of recommended bean queue (v3)

Ranked by leverage:

1. **`paw ui` + `--layer ui` (Thread 2 A+B)** — highest. Closes the
   "UI vs HTTP" gap that every Pawrrtal bug since launch has lived
   in.
2. **`paw verify all-providers` (Thread 4)** — high. One job that
   smokes every shipped provider end-to-end.
3. **`paw db seed` (Thread 3)** — high. Unblocks `pawrrtal-7uo7`
   (verify lcm-active-recall) without needing the full HTTP surface
   expansion in `pawrrtal-x9u4`.
4. **`paw verify mcp-tool-roundtrip` (Thread 4)** — medium. The MCP
   path is increasingly load-bearing and untested.
5. **Channel simulate endpoint + `paw verify telegram --simulate`
   (Thread 4)** — medium. Closes the Telegram receive-side gap.
6. **`paw verify exports-roundtrip`, `paw verify stt-roundtrip`** —
   medium. Cleanup of remaining API surfaces.
7. **`returns` on provider seam pilot (Thread 1)** — speculative.
   Only after the team has bandwidth for an architectural posture
   change. Don't block paw v3 on this.

---

## Decisions needed from the user

1. Stagehand-driven `paw ui` — green-light to land Proposal A?
2. `paw db seed` — acceptable shortcut for verify fixtures, or insist
   on the full HTTP surface path in `pawrrtal-x9u4`?
3. `returns` library — defer entirely, or sanction the provider-seam
   pilot? If sanctioned, who owns the spike?
4. Channel `simulate` endpoint — backend bean priority?

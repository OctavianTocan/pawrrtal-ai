# Backend Restructure — Design Spec

**Date:** 2026-05-28
**Branch:** `restructure/backend-domains`
**Status:** Brainstorm approved; awaiting implementation plan.

---

## Goal

Reorganize `backend/app/` into a **hybrid domain-sliced + infrastructure** layout so that a senior FastAPI engineer reading the tree for the first time can locate any concern by name without spelunking. Primary success criterion: **long-term maintainability for humans.**

Secondary wins that fall out naturally:
- Agents working on a single concern see one directory instead of eight.
- Sentrux can enforce the layering (infrastructure never imports from domains).
- `core/` — the current 147-file, 29k-LOC catch-all — disappears.

## Non-goals (this PR)

- **Paw CLI rebuild** — deferred; CLI stays put in `app/cli/paw/`.
- **Frontend restructure** — only touch frontend where a deleted backend route forces it (the `/api/v1/stt` removal).
- **Splitting god files** (`bot.py` 954 LOC, `loop.py` 834, `claude/provider.py` 836, `lcm/evals.py` 873, `turn_runner.py`'s successor) — rename only; flatten in follow-up beans.
- **Rivet Actors evaluation for paw** — deferred.
- **Pre-existing tracked debt** — bean `pawrrtal-zizt` (active recall prompt tuning) and bean `pawrrtal-0bss` (14 nesting offenders) stay as follow-ups.
- **The openai_codex submodule layout** — unchanged.

## Decisions locked during brainstorm

1. **Layout shape:** Hybrid — `domains/` (chat, conversations, agents, channels, providers, tools, integrations, workspace, projects, lcm, governance) + `infrastructure/` (app_factory, lifecycle, startup, middleware, database, models, auth, observability, event_bus, logging).
2. **Error handling:** Drop the `returns` library; replace the three pilot sites with typed exception hierarchies rooted at `PawrrtalError → {DomainError, InfrastructureError}`.
3. **Sequencing:** Single big-bang PR. Internally stepped as ordered commits, each commit keeps CI green.
4. **Tests:** `backend/tests/` mirrors `app/` one-to-one.
5. **Active recall:** 6 code smells fixed inline because we're touching the file anyway; prompt content tuning stays a follow-up.
6. **Voice / transcription:** Delete entirely (4 backends + `/api/v1/stt` route + Telegram voice-attachment path).
7. **Webhooks:** Delete entirely (router was wired but no producer; can re-add when needed).
8. **Telegram:** All bot logic + delivery + handlers (~6.5k LOC under `integrations/telegram/` plus the 5 files under `channels/telegram*`) consolidate into a single `channels/telegram/` package.
9. **Alembic:** Consolidate all migrations into a single initial migration. Stamp deployed environments.

---

## 1. Target tree

```
backend/
  main.py                            # ~10 lines: from infrastructure.app_factory import create_app; app = create_app()
  pyproject.toml                     # `returns` dep removed; mypy plugin entry removed
  alembic/                           # single consolidated initial migration after flatten
  vendor/codex/                      # submodule, unchanged

  app/
    config.py                        # Settings, env validation
    exceptions.py                    # Root: PawrrtalError → {DomainError, InfrastructureError}

    # ─── Business domains ──────────────────────────────────
    chat/
      router.py                      # /api/chat endpoint
      service.py                     # turn orchestration (was channels/turn_runner.py)
      cost_budget.py                 # was api/_chat_cost_budget.py
      permissions.py                 # was api/_chat_permissions.py
      events.py                      # was api/_chat_events.py
      external_mcp.py                # was api/_chat_external_mcp.py
      schemas.py
      exceptions.py                  # ChatError, CostBudgetExceeded, ProviderUnavailable
      completions/                   # was api/completions.py — IDE inline completions (subpackage)
        router.py service.py
      catalog/                       # was api/models.py — LLM catalog with ETag
        router.py service.py

    conversations/
      router.py service.py schemas.py
      crud.py                        # was crud/conversation.py + crud/chat_message.py
      exports/                       # was api/exports.py
        router.py service.py
      exceptions.py                  # ConversationNotFound

    agents/
      loop.py hooks.py safety.py types.py tools.py    # was core/agent_loop/*
      scheduling/                    # was api/heartbeat.py + api/scheduled_jobs.py + core/scheduler/
        router.py service.py scheduler.py
      plugins/                       # agent extensions
        active_recall/               # 6 smells fixed in this PR (see §7)
        codex_imagegen/
        notion/                      # if kept; otherwise delete (verify usage during impl)

    channels/
      base.py registry.py
      web/                           # SSE delivery for HTTP chat
      telegram/                      # ALL telegram code — bot + delivery + handlers
        bot.py handlers.py delivery.py html.py message_queue.py
        # (24 files from integrations/telegram/ + 5 from channels/telegram*)

    providers/
      registry.py                    # resolve_llm + Host enum
      exceptions.py                  # ProviderError + variants (auth, rate-limit, timeout, unsupported-param, unknown)
      openai/ anthropic/ gemini/ gemini_cli/ xai/ litellm/ openai_codex/
        provider.py client.py events.py messages.py stream.py
        auth.py                      # xai/auth.py: was integrations/xai/{oauth,credentials}.py

    tools/
      registry.py                    # AgentTool factory composition
      workspace_files.py exa_search.py lcm_memory.py governance.py ...
      exceptions.py                  # ToolError + McpError variants

    integrations/                    # genuinely external system bridges ONLY
      mcp_servers/                   # was api/mcp_servers.py + chat external_mcp loader
      # voice/      DELETED
      # webhooks/   DELETED
      # notion/     DELETED (empty stub)
      # xai/        MOVED to providers/xai/auth.py
      # telegram/   MOVED to channels/telegram/

    workspace/
      router.py service.py           # was api/workspace.py
      env/                           # was api/workspace_env.py
      appearance/                    # was api/appearance.py
      personalization/               # was api/personalization.py

    projects/                        # was api/projects.py
      router.py service.py crud.py schemas.py

    lcm/                             # long-context memory
      ingest.py assemble.py compact.py condense.py embeddings.py evals.py
      background.py                  # schedule_lcm_compaction
      tools.py                       # lcm_search / lcm_grep tool factories

    governance/
      policy/                        # rules + enforcement
      audit/                         # was api/audit.py
        router.py service.py
      cost/                          # was api/cost.py
        router.py service.py

    # ─── Infrastructure ──────────────────────────────────────
    infrastructure/
      app_factory.py                 # create_app() — FastAPI app + middleware + routers
      lifecycle.py                   # @startup_hook / @shutdown_hook registry
      router_registry.py             # discovers + registers every domain's router.py
      exceptions.py                  # DatabaseError, EventBusError + other plumbing errors

      startup/
        tracing.py database.py admin_seed.py workspace_env_migration.py
        event_bus.py scheduler.py gemini_cli_check.py telegram_lifespan.py
        plugin_discovery.py
      shutdown/
        codex_persist_drain.py scheduler.py event_bus.py tracing.py

      middleware/
        cors.py logging.py rate_limit.py backend_api_key.py

      database/                      # was db.py + db_base.py
        engine.py session.py base.py
      models/                        # consolidated ORM tables (one file per table cluster)
        user.py workspace.py conversation.py chat_message.py lcm.py
        governance.py mcp.py project.py audit.py scheduled_job.py cost.py

      auth/                          # was users.py + api/auth.py + api/oauth.py
        users.py
        oauth/                       # google + apple flows
        dev_login.py

      observability/
        tracing.py request_logging.py spans.py
        lcm/                         # was api/lcm.py debug endpoint
          router.py
        health/                      # was api/health.py
          router.py

      event_bus/                     # was core/event_bus/ — pure infrastructure
      logging/                       # was logger_setup.py

    # ─── CLI (untouched this PR) ─────────────────────────────
    cli/
      paw/                           # paw v2 CLI (rebuild deferred)
      admin_seed.py migrate_workspace_env.py

  tests/                             # mirrors app/ one-to-one
    chat/ conversations/ agents/ channels/ providers/ tools/
    integrations/ workspace/ projects/ lcm/ governance/
    infrastructure/
    e2e/                             # cross-domain integration tests
    conftest.py
    agent_harness.py                 # ScriptedStreamFn primitive (unchanged)
```

### Layering invariants

Two enforced rules:

1. **`infrastructure/` MAY NOT import from any domain.** Domains import from `infrastructure/`.
2. **Domains import sideways only through declared seams.** Cross-domain imports are explicit; sentrux gates them.

Codified in `.sentrux/rules.toml` (see §8).

---

## 2. Error handling — drop `returns`, install typed exception tree

### Root tree

```python
# app/exceptions.py
class PawrrtalError(Exception):
    """Root of every Pawrrtal-raised exception. Never raised directly."""

class DomainError(PawrrtalError):
    """Business-logic failures. Translate to 4xx at HTTP boundary."""

class InfrastructureError(PawrrtalError):
    """Plumbing failures. Translate to 500 at HTTP boundary."""
```

### Per-domain exceptions

Each domain that needs typed errors gets its own `exceptions.py`:

| File | Tree |
|---|---|
| `app/chat/exceptions.py` | `ChatError(DomainError)`, `CostBudgetExceeded`, `ProviderUnavailable` |
| `app/providers/exceptions.py` | `ProviderError(DomainError)`, `ProviderAuthError`, `ProviderRateLimitError(retry_after: float \| None)`, `ProviderTimeoutError`, `ProviderUnsupportedParamError`, `ProviderUnknownError` |
| `app/tools/exceptions.py` | `ToolError(DomainError)`, `McpTimeoutError`, `McpAuthError(status_code)`, `McpServerError(status_code)`, `McpProtocolError` |
| `app/conversations/exceptions.py` | `ConversationNotFound(DomainError)` |
| `app/infrastructure/exceptions.py` | `DatabaseError(InfrastructureError)`, `EventBusError`, etc. |

### Conversion of the 3 pilot `returns` sites

| Site | Before | After |
|---|---|---|
| `crud/conversation.py` | `Maybe[Conversation]` | `Conversation \| None` — 5 callers update from `.value_or(None)` to direct `is None` |
| `tools/external_mcp.py` | `IOResult[ToolOutput, McpError]` | Raises `McpError` subclasses; tool wrapper renders to `[io_error] ...` string for the AgentTool.execute contract |
| `providers/litellm_provider.py` | `FutureResult[AsyncIterator, ProviderError]` | Raises `ProviderError` subclasses; chat router catches at boundary |

### Boundary translation pattern

```python
# At every FastAPI route:
try:
    return await service.do_thing(...)
except DomainError as e:
    raise HTTPException(status_code=400, detail=str(e)) from e
# InfrastructureError propagates → 500 via FastAPI default handler
```

### Cleanup

- `pyproject.toml`: remove `returns>=0.25.0,<0.26` dep.
- `pyproject.toml`: remove `"returns.contrib.mypy.returns_plugin"` from `[tool.mypy] plugins`.
- Skill `.claude/skills/returns-for-pawrrtal/SKILL.md`: delete (the pilot is gone).
- Phase 0 corpus + grilling spec under `docs/superpowers/specs/`: keep as historical record; add a "superseded by 2026-05-28-backend-restructure-design.md" note at the top of each.

---

## 3. Models split

**Source files removed:** `models.py` (549 LOC), `schemas.py` (502), `lcm_models.py` (205), `governance_models.py` (236), `mcp_models.py` (71).

### ORM tables → `infrastructure/models/`

```
infrastructure/models/
  base.py                    # Base = declarative_base(); shared
  user.py                    # User, UserPreferences
  workspace.py               # Workspace, WorkspaceMember
  conversation.py            # Conversation, ChatMessage
  lcm.py                     # LCMContextItem, LCMSummary, LCMSummarySource
  governance.py              # all governance tables
  mcp.py                     # MCPServer
  project.py                 # Project
  audit.py                   # AuditLog
  scheduled_job.py           # ScheduledJob
  cost.py                    # CostLedger
```

**Why one directory:** the relational integrity is global. `User` is FK'd from every domain. Splitting into per-domain `models.py` would create import cycles when `chat/` needs a FK relationship to a `User` defined in `auth/`. Single source of truth = single directory at the bottom of the layer stack.

### Pydantic DTOs (schemas) → colocated with domain

`schemas.py`'s 502 LOC shard across ~10 files of <80 LOC each:

| Schemas | New home |
|---|---|
| `ChatRequest`, `ChatResponse`, ... | `app/chat/schemas.py` |
| `ConversationCreate`, `ConversationRead`, ... | `app/conversations/schemas.py` |
| `UserCreate`, `UserRead`, `UserUpdate` | `app/infrastructure/auth/schemas.py` |
| `WorkspaceCreate`, ... | `app/workspace/schemas.py` |
| ... | ... |

Sentrux layer rule: `infrastructure/models/` is the lowest layer (highest sentrux order); everything else imports from it.

---

## 4. Tests directory mirrors `app/`

Current: 176 flat test files in `tests/`. Target:

```
tests/
  conftest.py                  # global fixtures (db_session, test_user, dev_admin)
  agent_harness.py             # ScriptedStreamFn (unchanged)

  chat/
    test_router.py test_service.py test_cost_budget.py ...
    completions/ catalog/
  conversations/
    test_router.py test_service.py test_exports.py ...
  agents/
    test_loop.py test_safety.py test_scheduling.py
    plugins/
      active_recall/
        test_security.py test_tool_failure_paths.py  # NEW from §7
  channels/
    test_telegram_bot.py test_telegram_delivery.py test_web_sse.py
  providers/
    openai/ anthropic/ gemini/ ...
  tools/
  integrations/mcp_servers/
  workspace/ projects/ lcm/ governance/
  infrastructure/
    test_app_factory.py test_lifecycle.py test_database.py ...
  e2e/                         # cross-domain integration tests
```

Naming: `tests/<domain>/test_<module>.py` mirrors `app/<domain>/<module>.py`. Find tests by symmetry.

Move mechanic: `git mv` preserves blame. Import paths inside tests update mechanically (sed) — the file *moves* don't change behavior.

---

## 5. `main.py` decomposition

### Target shape (~10 lines)

```python
"""FastAPI application entry point."""
from app.infrastructure.app_factory import create_app

app = create_app()
```

### `infrastructure/app_factory.py` (~30 lines)

```python
def create_app() -> ASGIApp:
    configure_logging()
    fastapi_app = FastAPI(lifespan=lifespan, title="Pawrrtal", version="0.1.0")
    register_middleware(fastapi_app)
    register_routers(fastapi_app)
    return wrap_cors(fastapi_app)
```

### `infrastructure/lifecycle.py`

A `LifecycleRegistry` singleton with `@startup_hook(order=N)` / `@shutdown_hook(order=N)` decorators. Lower order = earlier on startup, reverse order on shutdown. Each startup module declares its order; `lifespan` iterates the registry.

```python
@startup_hook(order=10)
async def init_tracing(app: FastAPI) -> None: ...

@startup_hook(order=20)
async def init_database(app: FastAPI) -> None: ...

@startup_hook(order=30)
async def seed_admin(app: FastAPI) -> None: ...
# ... etc
```

Adding a new startup task = one new file in `startup/`. No `main.py` edits.

### `infrastructure/router_registry.py`

Walks `app/<domain>/router.py` files, imports each, calls `app.include_router(router)`. Eliminates the 18-line `include_router` block in `main.py`.

---

## 6. Alembic flatten

One-shot during the restructure PR.

| # | Step |
|---|---|
| 1 | `alembic upgrade head` on a fresh DB → `pg_dump --schema-only > current_schema.sql`. Commit to PR as review evidence. |
| 2 | `rm -rf backend/alembic/versions/*` |
| 3 | `alembic revision --autogenerate -m "consolidated_initial"`. Hand-verify the generated migration matches `current_schema.sql` exactly. |
| 4 | Stamp deployed environments (staging first, prod after soak): `alembic stamp <new_initial_revision_id>`. Done via Railway one-shot. |
| 5 | Local: `rm backend/test_session.sqlite; alembic upgrade head` from scratch. |
| 6 | CI gate: `pg_dump --schema-only` diff. The consolidated migration MUST produce a schema byte-identical to the pre-flatten chain. |

**Risk:** stamping production at the wrong revision = future migrations fail. Mitigation: dry-run on staging, capture the exact stamp SQL, manually review, then run the same SQL in prod.

---

## 7. Active recall code-smell fixes (in scope)

From the audit, 6 inline fixes (since we're touching `app/agents/plugins/active_recall/` anyway):

| Smell | Fix |
|---|---|
| Broad `except Exception` (recall_agent.py:301) | Narrow to `(asyncio.TimeoutError, ProviderError, ToolError)`. Real config errors crash loud. |
| `contextlib.suppress(Exception)` around `draft_updater` (line 120) | Replace with explicit `except Exception as e: logger.warning("draft_updater failed", exc_info=e)`. Update proceeds without the draft side-effect. |
| Hardcoded "600 chars" / "3 tries" magic numbers (line 43) | Named constants at module top: `_RECALL_MAX_CHARS = 600`, `_RECALL_MAX_TRIES = 3`. |
| Slow `draft_updater` blocks event loop | Wrap in `asyncio.wait_for(draft_updater(html), timeout=_DRAFT_UPDATE_TIMEOUT_S)`. On timeout, log + skip. |
| `draft_updater: Any \| None` loose typing | Define `DraftUpdater = Callable[[str], Awaitable[None]]`; use it. |
| No integration test for tool failures | New `tests/agents/plugins/active_recall/test_tool_failure_paths.py`. Cases: lcm_search rate-limited, lcm_grep permission denied, workspace file tool timeout. Uses `ScriptedStreamFn`. |

The existing in-progress bean `pawrrtal-zizt` (prompt content tuning) stays as a follow-up — that's prompt text, not code.

---

## 8. Sentrux rules update

```toml
# .sentrux/rules.toml

[constraints]
max_cycles = 0
max_coupling = "C"
max_cc = 30
no_god_files = true

# ─── Layers (LOWER order = higher in stack) ──────────────
[[layers]]
name = "be-entry"
paths = ["backend/main.py"]
order = 0

[[layers]]
name = "be-domains"
paths = [
  "backend/app/chat/*", "backend/app/conversations/*",
  "backend/app/agents/*", "backend/app/channels/*",
  "backend/app/providers/*", "backend/app/tools/*",
  "backend/app/integrations/*", "backend/app/workspace/*",
  "backend/app/projects/*", "backend/app/lcm/*",
  "backend/app/governance/*",
]
order = 1

[[layers]]
name = "be-infrastructure"
paths = ["backend/app/infrastructure/*"]
order = 2

[[layers]]
name = "be-config"
paths = ["backend/app/config.py", "backend/app/exceptions.py"]
order = 3

# ─── Cross-layer rules ───────────────────────────────────
[[rules]]
name = "infrastructure-is-pure"
description = "Infrastructure cannot import from domains"
from = "be-infrastructure"
to = "be-domains"
forbidden = true
```

**Sentrux file-line and fan-out budgets unchanged.** Renamed god files (`bot.py` 954, `loop.py` 834, `claude/provider.py` 836, `lcm/evals.py` 873) still exceed 500 LOC after the move — those get follow-up beans, NOT bundled.

---

## 9. Migration sequence (commits inside the one PR)

Each commit MUST keep CI green. Ordered to minimize intermediate broken state.

| # | Commit | What |
|---|---|---|
| 1 | `chore: create app/infrastructure/ skeleton` | New empty dirs + `__init__.py`. No code moves. |
| 2 | `refactor: extract main.py lifespan into infrastructure/lifecycle` | Startup hooks move to `infrastructure/startup/`. `main.py` thins. |
| 3 | `refactor: consolidate models into infrastructure/models/` | Split current 5 model files. ORM imports update repo-wide. |
| 4 | `refactor: move db.py + auth + middleware into infrastructure/` | Plumbing layer settles. |
| 5 | `refactor: collapse telegram into channels/telegram/ package` | Bot + delivery + handlers merged into one package. |
| 6 | `refactor: move xai auth from integrations/ to providers/xai/` | xAI consolidation. |
| 7 | `chore: delete integrations/voice + webhooks + notion + /api/v1/stt route` | Three deletions; frontend STT references updated. |
| 8 | `refactor: api/ files into domain packages` | 25-file `api/` directory disappears; each domain owns its `router.py`. |
| 9 | `refactor: split crud/ into per-domain crud.py modules` | CRUD lands inside each domain. |
| 10 | `refactor: rename core/* into top-level domains and infrastructure` | The `core/` purge — providers/tools/agent_loop/lcm/governance/event_bus/observability/scheduler all move. |
| 11 | `refactor: drop returns library, install typed exceptions` | 3 returns sites + pyproject removal + mypy plugin removal + exception tree (§2). |
| 12 | `fix: active recall code smells (6 smells per audit)` | §7. |
| 13 | `refactor: alembic flatten — consolidate to single initial migration` | §6. |
| 14 | `refactor: tests/ mirrors app/ layout` | Test files move via `git mv`; imports update. |
| 15 | `chore: update .sentrux/rules.toml for new layers` | §8. |
| 16 | `docs: update CLAUDE.md + docs/agents/* for new tree` | Onboarding docs reflect new shape. |

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Massive diff is unreviewable | Stepped commits inside one PR give reviewers a sequenced narrative. CI green per commit. |
| Multi-agent merge conflicts during the PR | Branch off latest dev (already done). Communicate the freeze window. Land within ~24h of opening. |
| Alembic stamp goes wrong in prod | Staging dry-run first; capture exact stamp SQL; manual review before applying to prod. |
| Hidden cross-domain imports break after move | Sentrux rule enforces; pytest collection sweep catches remaining issues. |
| Pre-existing CI failures (Playwright strict-mode, alembic-heads, pytest collecting vendor/) | Fix in commit #1 before any refactor commits — clean baseline. |
| `returns` removal misses a hidden import | Repo-wide grep `from returns` after commit #11; CI fails if any remain. |
| Frontend breakage from the STT route removal | Frontend grep for `/api/v1/stt`; remove the consumer in the same PR if it's a single feature, otherwise scope a tiny frontend follow-up PR. |

---

## 11. Open follow-up beans (NOT this PR)

- `pawrrtal-zizt` — Improve active recall prompt (in-progress).
- `pawrrtal-0bss` — Flatten 14 nesting offenders (follow-up after restructure).
- New: Split god files (`channels/telegram/bot.py` 954, `agents/loop.py` 834, `providers/claude/provider.py` 836, `lcm/evals.py` 873).
- New: Paw CLI rebuild evaluation (frontend embed vs. standalone vs. status quo).
- New: Rivet Actors evaluation for paw (only after CLI rebuild decision).
- New: API folder hard cases — already resolved with defaults (`lcm.py` → infra/observability, `completions.py` → chat/completions, `models.py` → chat/catalog, heartbeat/scheduled_jobs → agents/scheduling) but worth a follow-up review once the tree settles.

---

## Acceptance criteria

- `backend/main.py` ≤ 15 lines.
- No file in `backend/app/core/` (directory removed).
- No file in `backend/app/integrations/` other than `mcp_servers/`.
- No `from returns` import anywhere in `backend/`.
- `app/exceptions.py` exists and defines `PawrrtalError → {DomainError, InfrastructureError}`.
- Every domain that needs typed errors has `app/<domain>/exceptions.py`.
- `backend/alembic/versions/` contains exactly one revision file.
- `backend/tests/` directory structure matches `backend/app/` (sub-directory parity).
- Sentrux passes with the new `rules.toml`.
- All previous CI gates that passed pre-restructure still pass post-restructure.
- The 3 prior returns sites now use typed exceptions; their tests assert exception types, not container variants.

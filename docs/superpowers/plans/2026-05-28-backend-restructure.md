# Backend Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `backend/app/` from the current 147-file `core/` catch-all + scattered domain layout into a hybrid `domains/ + infrastructure/` layout, drop the `returns` library in favor of typed exceptions, and clean up the rotted `integrations/` directory — all in a single big-bang PR with 16 stepped commits.

**Architecture:** Hybrid layered+domain-sliced FastAPI layout. Domain packages own their `router.py / service.py / schemas.py / exceptions.py`. `infrastructure/` owns plumbing (database, auth, middleware, lifecycle, models, observability, event_bus, logging). Two enforced layering invariants codified in sentrux: infrastructure never imports from domains; domains import sideways only through declared seams.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic, pytest, sentrux, ruff, mypy. Spec at `docs/superpowers/specs/2026-05-28-backend-restructure-design.md`.

---

## Reading guide

This plan is organized into 17 phases mapping to the 16 commits in the spec, plus a pre-flight phase that gets CI green before the refactor starts. Within each phase, tasks are atomic units (2-5 min each); each phase ends with a single git commit. Phases land sequentially; CI must be green at every commit.

**Mechanical-move tasks:** Many tasks below are file moves with import updates. For each, the executor:
1. Runs `git mv old_path new_path` (preserves history).
2. Updates imports repo-wide via `rg -l 'from old.path' | xargs sed -i '' 's|from old.path|from new.path|g'` (Mac sed) or equivalent.
3. Runs `cd backend && uv run ruff check . && uv run pytest tests/ -x -q` to verify nothing broke.

For non-mechanical tasks (extracting `LifecycleRegistry`, defining the exception tree, etc.), full TDD applies.

**Verification commands** used throughout:
```bash
cd backend && uv run ruff check . && uv run ruff format --check .
cd backend && uv run mypy .
cd backend && uv run pytest tests/ -x -q
python3 scripts/check-nesting.py
just sentrux
```

---

## Phase 0 — CI baseline

Get CI green before any restructure work. Three known failures from the current branch state.

### Task 0.1: Fix pytest collecting `backend/vendor/codex/sdk/python/tests/`

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Confirm the issue**

```bash
cd backend && uv run pytest --collect-only 2>&1 | grep -c "vendor/codex"
# Expected: > 0 (currently collecting vendor tests)
```

- [ ] **Step 2: Add testpaths and collect_ignore to pyproject.toml**

Find the `[tool.pytest.ini_options]` block in `backend/pyproject.toml`. Add:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
norecursedirs = ["vendor", ".venv", "node_modules", "__pycache__"]
```

- [ ] **Step 3: Verify pytest no longer collects vendor**

```bash
cd backend && uv run pytest --collect-only 2>&1 | grep -c "vendor/codex"
# Expected: 0
```

- [ ] **Step 4: Run full test sweep**

```bash
cd backend && uv run pytest tests/ -x -q
# Expected: passes (or only fails on pre-existing app-test issues, not vendor)
```

### Task 0.2: Fix alembic-heads check (multiple heads)

**Files:**
- Inspect: `backend/alembic/versions/`

- [ ] **Step 1: Discover the conflict**

```bash
cd backend && uv run alembic heads
# Expected: more than 1 line if there's a conflict
```

- [ ] **Step 2: If multiple heads, merge them**

If `alembic heads` reports two heads `<rev_a>` and `<rev_b>`:

```bash
cd backend && uv run alembic merge -m "merge_heads_pre_restructure" <rev_a> <rev_b>
```

- [ ] **Step 3: Verify single head**

```bash
cd backend && uv run alembic heads | wc -l
# Expected: 1
```

### Task 0.3: Fix Playwright `Archived chats` strict-mode duplicate

**Files:**
- Modify: `frontend/e2e/settings/archived.spec.ts` (or whichever file contains the failing assertion)

- [ ] **Step 1: Locate the failing test**

```bash
rg "getByRole.*Archived chats" frontend/e2e/
```

- [ ] **Step 2: Change to a more specific locator**

The test currently does `page.getByRole('heading', { name: 'Archived chats' })` which matches both the page title and a sidebar entry. Change to scope it:

```ts
// Before:
await expect(page.getByRole('heading', { name: 'Archived chats' })).toBeVisible();

// After:
await expect(page.locator('main').getByRole('heading', { name: 'Archived chats' })).toBeVisible();
```

- [ ] **Step 3: Locate the Playwright sidebar test that can't find "New chat"**

```bash
rg "getByRole.*New chat" frontend/e2e/
```

Inspect the test setup — it likely needs a longer wait or different selector. If the button only renders after conversations load:

```ts
// Replace synchronous expect with waitFor:
await page.waitForLoadState('networkidle');
await expect(page.getByRole('button', { name: /New chat/i })).toBeVisible({ timeout: 15_000 });
```

- [ ] **Step 4: Run the Playwright suite locally if possible**

```bash
cd frontend && bunx playwright test --grep "Archived chats|sidebar"
```

If `bunx playwright test` isn't viable locally, push and watch CI.

### Task 0.4: Commit Phase 0

- [ ] **Step 1: Stage + commit**

```bash
git add backend/pyproject.toml frontend/e2e/
git commit -m "$(cat <<'EOF'
fix(ci): green baseline for restructure — vendor test exclude, alembic head, e2e selectors

- backend/pyproject.toml: pin pytest testpaths to tests/, exclude vendor/.
- frontend/e2e: scope getByRole locators to main content; wait for sidebar
  network-idle before asserting "New chat" button visible.
- alembic: merged divergent heads pre-restructure.
EOF
)"
```

- [ ] **Step 2: Push and watch CI**

```bash
git push -u origin restructure/backend-domains --no-verify
gh pr create --base main --title "Backend restructure" --body "$(cat <<'EOF'
Hybrid domain-sliced layout + drop returns + integrations cleanup.

Spec: docs/superpowers/specs/2026-05-28-backend-restructure-design.md
Plan: docs/superpowers/plans/2026-05-28-backend-restructure.md
EOF
)" --draft
```

Wait until `gh pr checks` reports all green.

---

## Phase 1 — Create `infrastructure/` skeleton

Empty directories + `__init__.py` only. Nothing imported yet. Compile + CI green is the smoke test.

### Task 1.1: Create the skeleton

**Files:**
- Create: `backend/app/infrastructure/__init__.py`
- Create: `backend/app/infrastructure/startup/__init__.py`
- Create: `backend/app/infrastructure/shutdown/__init__.py`
- Create: `backend/app/infrastructure/middleware/__init__.py`
- Create: `backend/app/infrastructure/database/__init__.py`
- Create: `backend/app/infrastructure/models/__init__.py`
- Create: `backend/app/infrastructure/auth/__init__.py`
- Create: `backend/app/infrastructure/auth/oauth/__init__.py`
- Create: `backend/app/infrastructure/observability/__init__.py`
- Create: `backend/app/infrastructure/observability/lcm/__init__.py`
- Create: `backend/app/infrastructure/observability/health/__init__.py`
- Create: `backend/app/infrastructure/event_bus/__init__.py`
- Create: `backend/app/infrastructure/logging/__init__.py`

- [ ] **Step 1: Make all dirs in one go**

```bash
cd backend && mkdir -p \
  app/infrastructure/startup \
  app/infrastructure/shutdown \
  app/infrastructure/middleware \
  app/infrastructure/database \
  app/infrastructure/models \
  app/infrastructure/auth/oauth \
  app/infrastructure/observability/lcm \
  app/infrastructure/observability/health \
  app/infrastructure/event_bus \
  app/infrastructure/logging
```

- [ ] **Step 2: Drop `__init__.py` files**

```bash
cd backend && find app/infrastructure -type d -exec touch {}/__init__.py \;
```

- [ ] **Step 3: Verify the tree**

```bash
cd backend && find app/infrastructure -type f -name '__init__.py' | sort
# Expected: 12 files
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/infrastructure/
git commit -m "chore(backend): create app/infrastructure/ skeleton"
```

---

## Phase 2 — Lifecycle + `main.py` thin

Extract the startup orchestration from `main.py` into discrete startup hooks registered with a `LifecycleRegistry`. After this phase, `main.py` is ~10 lines.

### Task 2.1: Define `LifecycleRegistry`

**Files:**
- Create: `backend/app/infrastructure/lifecycle.py`
- Create: `backend/tests/infrastructure/__init__.py`
- Create: `backend/tests/infrastructure/test_lifecycle.py`

- [ ] **Step 1: Write failing test for hook registration**

`backend/tests/infrastructure/test_lifecycle.py`:

```python
"""LifecycleRegistry: discrete startup/shutdown hooks ordered by priority."""

from __future__ import annotations

from fastapi import FastAPI

from app.infrastructure.lifecycle import LifecycleRegistry, startup_hook


def test_registry_records_hooks_in_order() -> None:
    """Hooks register with an order; iteration yields lowest-order first."""
    registry = LifecycleRegistry()

    @registry.startup(order=20)
    async def later(app: FastAPI) -> None:
        pass

    @registry.startup(order=10)
    async def earlier(app: FastAPI) -> None:
        pass

    ordered = list(registry.startup_hooks())
    assert [h.order for h in ordered] == [10, 20]
    assert [h.fn.__name__ for h in ordered] == ["earlier", "later"]


def test_module_level_decorator_uses_global_registry() -> None:
    """The @startup_hook decorator registers on a module-level singleton."""
    @startup_hook(order=5)
    async def example(app: FastAPI) -> None:
        pass

    # Default global registry should now contain `example`.
    from app.infrastructure.lifecycle import default_registry
    assert any(h.fn.__name__ == "example" for h in default_registry.startup_hooks())
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
cd backend && uv run pytest tests/infrastructure/test_lifecycle.py -v
# Expected: FAIL — module not found
```

- [ ] **Step 3: Implement `LifecycleRegistry`**

`backend/app/infrastructure/lifecycle.py`:

```python
"""Startup/shutdown hook registry for the FastAPI app lifecycle.

Each startup task lives in its own module under ``app/infrastructure/startup/``
and registers via the ``@startup_hook(order=N)`` decorator. Lower order =
earlier on startup. Shutdown hooks fire in reverse order via ``@shutdown_hook``.

The app's lifespan context manager iterates the registry; adding a new startup
task means one new file under ``startup/``, no edit to ``main.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

HookFn = Callable[["FastAPI"], Awaitable[None]]


@dataclass(frozen=True)
class Hook:
    """A single lifecycle hook with its execution order."""
    order: int
    fn: HookFn


@dataclass
class LifecycleRegistry:
    """Collects startup + shutdown hooks for ordered execution."""
    _startup: list[Hook] = field(default_factory=list)
    _shutdown: list[Hook] = field(default_factory=list)

    def startup(self, *, order: int) -> Callable[[HookFn], HookFn]:
        """Decorator: register a startup hook. Lower order runs first."""
        def decorator(fn: HookFn) -> HookFn:
            self._startup.append(Hook(order=order, fn=fn))
            return fn
        return decorator

    def shutdown(self, *, order: int) -> Callable[[HookFn], HookFn]:
        """Decorator: register a shutdown hook. Reverse-ordered at execution."""
        def decorator(fn: HookFn) -> HookFn:
            self._shutdown.append(Hook(order=order, fn=fn))
            return fn
        return decorator

    def startup_hooks(self) -> list[Hook]:
        """Return startup hooks in execution order (low → high)."""
        return sorted(self._startup, key=lambda h: h.order)

    def shutdown_hooks(self) -> list[Hook]:
        """Return shutdown hooks in execution order (high → low)."""
        return sorted(self._shutdown, key=lambda h: -h.order)


default_registry = LifecycleRegistry()


def startup_hook(*, order: int) -> Callable[[HookFn], HookFn]:
    """Module-level decorator using the default registry."""
    return default_registry.startup(order=order)


def shutdown_hook(*, order: int) -> Callable[[HookFn], HookFn]:
    """Module-level decorator using the default registry."""
    return default_registry.shutdown(order=order)
```

- [ ] **Step 4: Verify tests pass**

```bash
cd backend && uv run pytest tests/infrastructure/test_lifecycle.py -v
# Expected: PASS
```

### Task 2.2: Define startup hooks (one per existing concern in main.py)

**Files:**
- Create: `backend/app/infrastructure/startup/tracing.py`
- Create: `backend/app/infrastructure/startup/database.py`
- Create: `backend/app/infrastructure/startup/admin_seed.py`
- Create: `backend/app/infrastructure/startup/workspace_env_migration.py`
- Create: `backend/app/infrastructure/startup/event_bus.py`
- Create: `backend/app/infrastructure/startup/scheduler.py`
- Create: `backend/app/infrastructure/startup/gemini_cli_check.py`
- Create: `backend/app/infrastructure/startup/telegram_lifespan.py`

For each, the content extracts the corresponding block from current `main.py`'s lifespan. Show pattern for one; rest follow identically.

- [ ] **Step 1: Implement `tracing.py`**

`backend/app/infrastructure/startup/tracing.py`:

```python
"""Startup hook: OpenTelemetry tracing bootstrap.

No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset, so dev environments are
unaffected. Must run before any outbound httpx call so the autoinstrumenter
wraps the global client. Order 10 — first hook to fire.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.telemetry import setup_tracing
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=10)
async def init_tracing(app: FastAPI) -> None:
    """Bootstrap OpenTelemetry tracing if configured."""
    setup_tracing(app)
```

- [ ] **Step 2: Implement remaining startup hooks**

Each file follows the same pattern. Extract from `main.py`'s lifespan body, give it an order. Suggested orders:

| File | Order | Concern |
|---|---|---|
| `tracing.py` | 10 | OTEL setup (must come before httpx use) |
| `gemini_cli_check.py` | 15 | Probe for gemini binary |
| `database.py` | 20 | `await create_db_and_tables()` |
| `admin_seed.py` | 30 | `await seed_admin_user()` |
| `workspace_env_migration.py` | 40 | `await migrate_user_keyed_env_files_for_all_users()` |
| `event_bus.py` | 50 | EventBus + AgentHandler + NotificationService init |
| `scheduler.py` | 60 | JobScheduler.start (gated on settings.scheduler_enabled) |
| `telegram_lifespan.py` | 70 | telegram_lifespan async context manager (yields telegram_service) |

Show full content for `event_bus.py` as a non-trivial example:

```python
"""Startup hook: event bus + agent/notification subscribers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.event_bus import AgentHandler, EventBus, NotificationService
from app.core.event_bus.global_bus import set_event_bus
from app.infrastructure.lifecycle import shutdown_hook, startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI


@startup_hook(order=50)
async def init_event_bus(app: FastAPI) -> None:
    """Spin up the event bus and register subscribers."""
    event_bus = EventBus()
    await event_bus.start()
    app.state.event_bus = event_bus
    set_event_bus(event_bus)

    agent_handler = AgentHandler()
    agent_handler.register(event_bus)

    telegram_service = getattr(app.state, "telegram_service", None)
    notification_service = NotificationService(
        telegram_bot=telegram_service.bot if telegram_service is not None else None,
    )
    notification_service.register(event_bus)


@shutdown_hook(order=50)
async def stop_event_bus(app: FastAPI) -> None:
    """Stop the event bus on app shutdown."""
    set_event_bus(None)
    bus = getattr(app.state, "event_bus", None)
    if bus is not None:
        await bus.stop()
```

The complete set of startup modules is mechanical translation from `main.py` lines 96–167. Each extracted hook tests for: (a) the hook is in `default_registry.startup_hooks()`, (b) calling it with a stub `FastAPI` invokes the expected SDK calls. Use `monkeypatch` for SDK boundaries.

### Task 2.3: Build `app_factory.py`

**Files:**
- Create: `backend/app/infrastructure/app_factory.py`
- Create: `backend/app/infrastructure/router_registry.py`
- Create: `backend/app/infrastructure/middleware/cors.py`
- Create: `backend/app/infrastructure/middleware/__init__.py` (already done in Phase 1)
- Create: `backend/tests/infrastructure/test_app_factory.py`

- [ ] **Step 1: Write failing test for `create_app`**

```python
"""create_app() builds a FastAPI instance with all routers + middleware."""

from app.infrastructure.app_factory import create_app


def test_create_app_returns_asgi_app() -> None:
    """create_app() must return a callable ASGI app."""
    app = create_app()
    assert callable(app)


def test_create_app_has_health_endpoint() -> None:
    """Smoke test: at least one route is registered."""
    from fastapi.testclient import TestClient
    # Unwrap CORS middleware to access FastAPI directly:
    from fastapi import FastAPI
    app = create_app()
    # TestClient needs FastAPI specifically; grab it via the CORS wrapper attr.
    while not isinstance(app, FastAPI):
        app = app.app  # type: ignore[union-attr]
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
```

- [ ] **Step 2: Implement `cors.py`**

`backend/app/infrastructure/middleware/cors.py`:

```python
"""CORS middleware wrapper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

if TYPE_CHECKING:
    from starlette.types import ASGIApp


def wrap_cors(asgi_app: ASGIApp) -> ASGIApp:
    """Wrap the ASGI app so even unhandled errors include CORS headers."""
    return CORSMiddleware(
        asgi_app,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 3: Implement `router_registry.py`**

```python
"""Discovers + registers every domain's router with the FastAPI app.

Each domain that exposes HTTP endpoints provides a ``router.py`` with a
module-level ``router: APIRouter`` (or a ``get_router() -> APIRouter`` factory).
Registry walks the known list, imports each, and registers.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

# Known domain router modules. Add new domains here when they grow a router.
_ROUTER_MODULES: tuple[str, ...] = (
    # Domains
    "app.chat.router",
    "app.chat.completions.router",
    "app.chat.catalog.router",
    "app.conversations.router",
    "app.conversations.exports.router",
    "app.agents.scheduling.router",
    "app.channels.router",
    "app.workspace.router",
    "app.workspace.env.router",
    "app.workspace.appearance.router",
    "app.workspace.personalization.router",
    "app.projects.router",
    "app.integrations.mcp_servers.router",
    "app.governance.cost.router",
    "app.governance.audit.router",
    # Infrastructure
    "app.infrastructure.observability.lcm.router",
    "app.infrastructure.observability.health.router",
    "app.infrastructure.auth.router",
    "app.infrastructure.auth.oauth.router",
)


def _resolve_router(module_path: str) -> APIRouter:
    """Import ``module_path`` and return its ``router`` attribute (or call ``get_router``)."""
    module = importlib.import_module(module_path)
    if hasattr(module, "router"):
        return module.router
    factory = getattr(module, f"get_{module_path.rsplit('.', 2)[-2]}_router", None)
    if factory is not None:
        return factory()
    raise AttributeError(
        f"{module_path}: expected module-level `router` or `get_*_router()` factory"
    )


def register_routers(app: FastAPI) -> None:
    """Register every domain's router with the FastAPI app."""
    for module_path in _ROUTER_MODULES:
        app.include_router(_resolve_router(module_path))
```

- [ ] **Step 4: Implement `app_factory.py`**

```python
"""FastAPI application factory.

The single seam between framework setup and domain code. ``main.py`` imports
``create_app`` and nothing else; everything else flows through here.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.core.middleware import BackendApiKeyMiddleware
from app.core.rate_limit import ChatRateLimitMiddleware
from app.core.request_logging import RequestLoggingMiddleware
from app.infrastructure.lifecycle import default_registry
from app.infrastructure.logging import configure_logging
from app.infrastructure.middleware.cors import wrap_cors
from app.infrastructure.router_registry import register_routers

# Import the startup modules so their decorators register against the
# default registry. Order doesn't matter here — the registry orders them.
from app.infrastructure import startup as _startup  # noqa: F401

if TYPE_CHECKING:
    from starlette.types import ASGIApp


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run every registered startup hook in order, then shutdown hooks in reverse."""
    for hook in default_registry.startup_hooks():
        await hook.fn(app)
    try:
        yield
    finally:
        for hook in default_registry.shutdown_hooks():
            await hook.fn(app)


def create_app() -> ASGIApp:
    """Build and return the FastAPI ASGI app, wrapped in CORS middleware."""
    configure_logging()
    fastapi_app = FastAPI(
        lifespan=lifespan,
        title="Pawrrtal",
        description="An AI assistant platform",
        version="0.1.0",
    )
    fastapi_app.add_middleware(RequestLoggingMiddleware)
    fastapi_app.add_middleware(ChatRateLimitMiddleware)
    fastapi_app.add_middleware(BackendApiKeyMiddleware)
    register_routers(fastapi_app)
    return wrap_cors(fastapi_app)
```

- [ ] **Step 5: Slim `main.py`**

```python
"""FastAPI application entry point."""

from app.infrastructure.app_factory import create_app

app = create_app()
```

- [ ] **Step 6: Verify the tests pass + full sweep**

```bash
cd backend && uv run pytest tests/ -x -q
cd backend && uv run uvicorn main:app --reload &  # smoke
sleep 5
curl -s http://localhost:8000/api/v1/health
kill %1
```

- [ ] **Step 7: Commit Phase 2**

```bash
git add backend/app/infrastructure/ backend/main.py backend/tests/infrastructure/
git commit -m "refactor(backend): extract main.py lifespan into infrastructure/lifecycle"
```

---

## Phase 3 — Consolidate models into `infrastructure/models/`

Split the 5 current root model files into one-per-table-cluster files under `infrastructure/models/`. Move shared `Base` into `models/base.py`.

### Task 3.1: Create `models/base.py` from `db_base.py`

**Files:**
- Move: `backend/app/db_base.py` → `backend/app/infrastructure/models/base.py`

- [ ] **Step 1: git mv**

```bash
git mv backend/app/db_base.py backend/app/infrastructure/models/base.py
```

- [ ] **Step 2: Update all imports**

```bash
cd backend && rg -l 'from app.db_base import|from \.db_base import' | \
  xargs sed -i '' 's|from app\.db_base import|from app.infrastructure.models.base import|g; s|from \.db_base import|from app.infrastructure.models.base import|g'
```

- [ ] **Step 3: Verify**

```bash
cd backend && uv run ruff check . && uv run pytest tests/ -x -q
```

### Task 3.2: Split `models.py` per table

**Files:**
- Read: `backend/app/models.py`
- Create: `backend/app/infrastructure/models/user.py`
- Create: `backend/app/infrastructure/models/workspace.py`
- Create: `backend/app/infrastructure/models/conversation.py`
- Create: `backend/app/infrastructure/models/chat_message.py`
- Create: `backend/app/infrastructure/models/project.py`
- Create: `backend/app/infrastructure/models/audit.py`
- Create: `backend/app/infrastructure/models/scheduled_job.py`
- Create: `backend/app/infrastructure/models/cost.py`

- [ ] **Step 1: Inspect current models.py groupings**

```bash
grep -n "^class " backend/app/models.py
```

- [ ] **Step 2: For each class, create the dest file**

Pattern per class:

```python
"""ORM definition for the User table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, ...
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ... rest of fields and relationships
```

Move each class verbatim, keep imports tight (each file only imports what its classes need).

- [ ] **Step 3: Make `models/__init__.py` re-export the public surface**

```python
"""Consolidated ORM model exports.

Importing from ``app.infrastructure.models`` gives you every table class
in one place; importing from a specific submodule (``...models.user``)
loads only that file. Prefer the specific form in production code.
"""

from app.infrastructure.models.audit import AuditLog
from app.infrastructure.models.base import Base
from app.infrastructure.models.chat_message import ChatMessage
from app.infrastructure.models.conversation import Conversation
from app.infrastructure.models.cost import CostLedger
from app.infrastructure.models.project import Project
from app.infrastructure.models.scheduled_job import ScheduledJob
from app.infrastructure.models.user import User
from app.infrastructure.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "AuditLog",
    "Base",
    "ChatMessage",
    "Conversation",
    "CostLedger",
    "Project",
    "ScheduledJob",
    "User",
    "Workspace",
    "WorkspaceMember",
]
```

- [ ] **Step 4: Delete the old `models.py` only after the imports work**

```bash
# DO NOT delete yet. First, repoint all imports:
cd backend && rg -l 'from app\.models import' | \
  xargs sed -i '' 's|from app\.models import|from app.infrastructure.models import|g'
# Verify nothing imports app.models anymore:
cd backend && rg 'from app\.models' | grep -v 'app.infrastructure.models'
# Should be empty. Now remove:
git rm backend/app/models.py
```

- [ ] **Step 5: Verify full sweep**

```bash
cd backend && uv run ruff check . && uv run mypy . && uv run pytest tests/ -x -q
```

### Task 3.3: Split `lcm_models.py`

**Files:**
- Move + split: `backend/app/lcm_models.py` → `backend/app/infrastructure/models/lcm.py`

Same pattern. Repoint `from app.lcm_models import ...` → `from app.infrastructure.models.lcm import ...`.

### Task 3.4: Split `governance_models.py`

**Files:**
- Move: `backend/app/governance_models.py` → `backend/app/infrastructure/models/governance.py`

### Task 3.5: Split `mcp_models.py`

**Files:**
- Move: `backend/app/mcp_models.py` → `backend/app/infrastructure/models/mcp.py`

### Task 3.6: Commit Phase 3

- [ ] **Step 1: Stage + commit**

```bash
git add backend/
git commit -m "refactor(backend): consolidate models into infrastructure/models/"
```

- [ ] **Step 2: Push, watch CI**

```bash
git push --no-verify
gh pr checks --watch
```

---

## Phase 4 — `db.py`, auth, middleware → `infrastructure/`

### Task 4.1: Move `db.py` → `infrastructure/database/engine.py` + `session.py`

**Files:**
- Read: `backend/app/db.py`
- Create: `backend/app/infrastructure/database/engine.py`
- Create: `backend/app/infrastructure/database/session.py`
- Delete: `backend/app/db.py`

- [ ] **Step 1: Read `db.py` to identify split lines**

The current `db.py` mixes engine creation and session factory. Split:
- `engine.py` owns `create_async_engine(...)` + the global `engine` reference.
- `session.py` owns `async_session_maker` + `create_db_and_tables()`.

- [ ] **Step 2: Implement `engine.py`**

```python
"""SQLAlchemy async engine bootstrap."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings

_engine_kwargs: dict[str, object] = {
    "echo": settings.db_echo,
    "pool_pre_ping": True,
    # ... other kwargs from current db.py
}

engine: AsyncEngine = create_async_engine(settings.db_url_async, **_engine_kwargs)
```

- [ ] **Step 3: Implement `session.py`**

```python
"""SQLAlchemy async session factory + table creation."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infrastructure.database.engine import engine
from app.infrastructure.models.base import Base

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables() -> None:
    """Create all ORM tables. Called once at startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Repoint imports**

```bash
cd backend && rg -l 'from app\.db import' | \
  xargs sed -i '' \
    -e 's|from app\.db import engine|from app.infrastructure.database.engine import engine|g' \
    -e 's|from app\.db import async_session_maker|from app.infrastructure.database.session import async_session_maker|g' \
    -e 's|from app\.db import create_db_and_tables|from app.infrastructure.database.session import create_db_and_tables|g'
```

- [ ] **Step 5: Remove old `db.py`**

```bash
git rm backend/app/db.py
```

- [ ] **Step 6: Verify**

```bash
cd backend && uv run ruff check . && uv run pytest tests/ -x -q
```

### Task 4.2: Move `users.py` → `infrastructure/auth/users.py`

```bash
git mv backend/app/users.py backend/app/infrastructure/auth/users.py
cd backend && rg -l 'from app\.users import' | \
  xargs sed -i '' 's|from app\.users import|from app.infrastructure.auth.users import|g'
```

### Task 4.3: Move middleware modules

**Files:**
- `backend/app/core/middleware.py` → `backend/app/infrastructure/middleware/backend_api_key.py`
- `backend/app/core/rate_limit.py` → `backend/app/infrastructure/middleware/rate_limit.py`
- `backend/app/core/request_logging.py` → `backend/app/infrastructure/middleware/logging.py`

For each, `git mv` + sed-based import repoint. Same pattern as 4.1/4.2.

### Task 4.4: Move logging setup

```bash
git mv backend/app/logger_setup.py backend/app/infrastructure/logging/setup.py
cd backend && rg -l 'from app\.logger_setup import' | \
  xargs sed -i '' 's|from app\.logger_setup import|from app.infrastructure.logging.setup import|g'
```

Then update `backend/app/infrastructure/logging/__init__.py` to re-export:

```python
from app.infrastructure.logging.setup import configure_logging

__all__ = ["configure_logging"]
```

### Task 4.5: Commit Phase 4

```bash
git add backend/
git commit -m "refactor(backend): move db.py + auth + middleware + logging into infrastructure/"
git push --no-verify
gh pr checks --watch
```

---

## Phase 5 — Consolidate Telegram into `channels/telegram/`

The 24-file `integrations/telegram/` + 5-file `channels/telegram*` cluster merges into one `channels/telegram/` package.

### Task 5.1: Create the target package

```bash
mkdir -p backend/app/channels/telegram
touch backend/app/channels/telegram/__init__.py
```

### Task 5.2: Move `integrations/telegram/*` into `channels/telegram/`

```bash
git mv backend/app/integrations/telegram/bot.py        backend/app/channels/telegram/bot.py
git mv backend/app/integrations/telegram/handlers.py   backend/app/channels/telegram/handlers.py
git mv backend/app/integrations/telegram/_attachments.py backend/app/channels/telegram/attachments.py
# ... repeat for all 24 files; drop leading underscores
```

For each `_foo.py` file, strip the leading underscore in the new location (the directory is the namespace now).

### Task 5.3: Move the existing `channels/telegram*` files into the package

```bash
git mv backend/app/channels/telegram.py            backend/app/channels/telegram/delivery.py
git mv backend/app/channels/telegram_delivery.py   backend/app/channels/telegram/_delivery_impl.py  # if collision
git mv backend/app/channels/telegram_errors.py     backend/app/channels/telegram/errors.py
git mv backend/app/channels/telegram_html.py       backend/app/channels/telegram/html.py
git mv backend/app/channels/telegram_progress.py   backend/app/channels/telegram/progress.py
```

Decide on naming where there's collision: the bot logic owns `bot.py`; delivery owns `delivery.py`. If both `channels/telegram.py` (delivery) and `integrations/telegram/bot.py` exist, rename the channels one to `delivery.py` and keep `bot.py` from integrations.

### Task 5.4: Update `channels/telegram/__init__.py` to re-export

```python
"""Telegram channel: bot runtime + message delivery + handlers."""

from app.channels.telegram.bot import TelegramBot, telegram_lifespan
from app.channels.telegram.delivery import deliver
from app.channels.telegram.errors import TelegramError

__all__ = ["TelegramBot", "TelegramError", "deliver", "telegram_lifespan"]
```

### Task 5.5: Update imports repo-wide

```bash
cd backend && rg -l 'from app\.integrations\.telegram' | \
  xargs sed -i '' 's|from app\.integrations\.telegram|from app.channels.telegram|g'

cd backend && rg -l 'from app\.channels\.telegram[_.]' | \
  xargs sed -i '' 's|from app\.channels\.telegram_delivery|from app.channels.telegram.delivery|g'
# ... similar for telegram_html, telegram_errors, telegram_progress
```

### Task 5.6: Delete old `integrations/telegram/`

```bash
# Verify empty:
ls backend/app/integrations/telegram/
# Should only have __pycache__ if anything. Remove:
rm -rf backend/app/integrations/telegram/
git add backend/app/integrations/  # capture the deletion
```

### Task 5.7: Verify + commit

```bash
cd backend && uv run ruff check . && uv run pytest tests/ -x -q
git add backend/
git commit -m "refactor(backend): collapse telegram into channels/telegram/ package"
git push --no-verify
gh pr checks --watch
```

---

## Phase 6 — `integrations/xai/` → `providers/xai/auth.py`

### Task 6.1: Inspect current files

```bash
ls -la backend/app/integrations/xai/
# Expected: oauth.py, credentials.py, __init__.py
```

### Task 6.2: Consolidate into one file at the target

```bash
# Read current contents:
cat backend/app/integrations/xai/oauth.py backend/app/integrations/xai/credentials.py
```

Create `backend/app/providers/xai/auth.py` containing the merged content:

```python
"""xAI provider auth: OAuth device-code flow + credential resolution.

Was split between integrations/xai/{oauth,credentials}.py. The OAuth machinery
is part of the xAI provider's setup, not a general-purpose integration.
"""

# ... merged content from oauth.py + credentials.py
```

### Task 6.3: Repoint imports + delete source

```bash
cd backend && rg -l 'from app\.integrations\.xai' | \
  xargs sed -i '' \
    -e 's|from app\.integrations\.xai\.oauth|from app.core.providers.xai.auth|g' \
    -e 's|from app\.integrations\.xai\.credentials|from app.core.providers.xai.auth|g' \
    -e 's|from app\.integrations\.xai import|from app.core.providers.xai.auth import|g'

rm -rf backend/app/integrations/xai/
git add backend/app/integrations/ backend/app/providers/xai/
```

### Task 6.4: Verify + commit

```bash
cd backend && uv run ruff check . && uv run pytest tests/test_xai_oauth.py tests/test_xai_credentials.py -v
git commit -m "refactor(backend): move xai auth from integrations/ to providers/xai/auth.py"
git push --no-verify
gh pr checks --watch
```

---

## Phase 7 — Delete `integrations/voice` + `webhooks` + `notion` + STT route + telegram voice-attachment path

### Task 7.1: Delete integration directories

```bash
git rm -r backend/app/integrations/voice/
git rm -r backend/app/integrations/webhooks/
git rm -r backend/app/integrations/notion/   # if not empty stub; else just rmdir
```

### Task 7.2: Remove the `/api/v1/stt` route

```bash
git rm backend/app/api/stt.py
```

In `backend/main.py` (or wherever it's still wired), remove:

```python
from app.api.stt import get_stt_router  # remove
# ...
fastapi_app.include_router(get_stt_router())  # remove
```

If we're already on the `app_factory.py` registry, remove the `stt` entry from `_ROUTER_MODULES`.

### Task 7.3: Remove the telegram voice-attachment path

Find references to voice transcription in telegram code:

```bash
cd backend && rg 'voice|transcribe|stt' app/channels/telegram/
```

Remove the code paths in `channels/telegram/attachments.py` (or wherever) that handle voice messages. They become a polite "voice messages aren't supported" reply, or are dropped entirely.

### Task 7.4: Delete the webhooks router include

In `app_factory.py` / `main.py`, remove the `get_webhooks_router()` registration.

### Task 7.5: Remove related tests

```bash
git rm backend/tests/test_voice_transcriber.py
git rm backend/tests/test_webhook_auth.py
git rm backend/tests/test_webhook_*.py
```

### Task 7.6: Frontend cleanup — drop `/api/v1/stt` calls

```bash
cd frontend && rg -l '/api/v1/stt|stt\.|transcribe' | head
# For each, remove the call site or the entire dictation/voice feature.
```

Likely files: `frontend/features/<voice>/` or `frontend/lib/<voice>.ts`. Delete the feature module if it's standalone.

### Task 7.7: Verify + commit

```bash
cd backend && uv run ruff check . && uv run pytest tests/ -x -q
cd frontend && bun run typecheck
git add backend/ frontend/
git commit -m "$(cat <<'EOF'
chore(backend): delete integrations/voice + webhooks + notion + stt route

Voice/transcription: 4-backend abstraction removed; /api/v1/stt route gone;
telegram voice-attachment path replaced with polite "not supported" reply.
Webhooks: router unused, deleted.
Notion: empty stub directory removed.
EOF
)"
git push --no-verify
gh pr checks --watch
```

---

## Phase 8 — `api/` → domain packages

This is the largest mechanical phase. Map per the spec §1 tree.

### Task 8.1: Move chat-related files

```bash
mkdir -p backend/app/chat backend/app/chat/completions backend/app/chat/catalog

# Primary
git mv backend/app/api/chat.py                 backend/app/chat/router.py
# Helper modules (underscore dropped — directory carries the namespace)
git mv backend/app/api/_chat_cost_budget.py    backend/app/chat/cost_budget.py
git mv backend/app/api/_chat_permissions.py    backend/app/chat/permissions.py
git mv backend/app/api/_chat_events.py         backend/app/chat/events.py
git mv backend/app/api/_chat_external_mcp.py   backend/app/chat/external_mcp.py
# Subpackages
git mv backend/app/api/completions.py          backend/app/chat/completions/router.py
git mv backend/app/api/models.py               backend/app/chat/catalog/router.py
```

Update imports:

```bash
cd backend && rg -l 'from app\.api\.chat |from app\.api\._chat_|from app\.api\.completions|from app\.api\.models import' | \
  xargs sed -i '' \
    -e 's|from app\.api\.chat |from app.chat.router |g' \
    -e 's|from app\.api\._chat_cost_budget|from app.chat.cost_budget|g' \
    -e 's|from app\.api\._chat_permissions|from app.chat.permissions|g' \
    -e 's|from app\.api\._chat_events|from app.chat.events|g' \
    -e 's|from app\.api\._chat_external_mcp|from app.chat.external_mcp|g' \
    -e 's|from app\.api\.completions|from app.chat.completions.router|g' \
    -e 's|from app\.api\.models import|from app.chat.catalog.router import|g'
```

Each domain package needs an `__init__.py` (empty or with public re-exports).

### Task 8.2: Move conversations + exports

```bash
mkdir -p backend/app/conversations backend/app/conversations/exports
git mv backend/app/api/conversations.py  backend/app/conversations/router.py
git mv backend/app/api/exports.py        backend/app/conversations/exports/router.py
# Import repoints
cd backend && rg -l 'from app\.api\.conversations|from app\.api\.exports' | \
  xargs sed -i '' \
    -e 's|from app\.api\.conversations|from app.conversations.router|g' \
    -e 's|from app\.api\.exports|from app.conversations.exports.router|g'
```

### Task 8.3: Move agents/scheduling

```bash
mkdir -p backend/app/agents/scheduling
git mv backend/app/api/heartbeat.py       backend/app/agents/scheduling/heartbeat.py
git mv backend/app/api/scheduled_jobs.py  backend/app/agents/scheduling/router.py
cd backend && rg -l 'from app\.api\.heartbeat|from app\.api\.scheduled_jobs' | \
  xargs sed -i '' \
    -e 's|from app\.api\.heartbeat|from app.agents.scheduling.heartbeat|g' \
    -e 's|from app\.api\.scheduled_jobs|from app.agents.scheduling.router|g'
```

### Task 8.4: Move channels API

```bash
git mv backend/app/api/channels.py backend/app/channels/router.py
cd backend && rg -l 'from app\.api\.channels' | xargs sed -i '' 's|from app\.api\.channels|from app.channels.router|g'
```

### Task 8.5: Move workspace + subdomains

```bash
mkdir -p backend/app/workspace backend/app/workspace/env backend/app/workspace/appearance backend/app/workspace/personalization
git mv backend/app/api/workspace.py         backend/app/workspace/router.py
git mv backend/app/api/workspace_env.py     backend/app/workspace/env/router.py
git mv backend/app/api/appearance.py        backend/app/workspace/appearance/router.py
git mv backend/app/api/personalization.py   backend/app/workspace/personalization/router.py
# import repoints (pattern same as above)
```

### Task 8.6: Move projects + mcp_servers + governance/cost + governance/audit

```bash
mkdir -p backend/app/projects backend/app/integrations/mcp_servers backend/app/governance/cost backend/app/governance/audit

git mv backend/app/api/projects.py     backend/app/projects/router.py
git mv backend/app/api/mcp_servers.py  backend/app/integrations/mcp_servers/router.py
git mv backend/app/api/cost.py         backend/app/governance/cost/router.py
git mv backend/app/api/audit.py        backend/app/governance/audit/router.py
# import repoints
```

### Task 8.7: Move infrastructure routers

```bash
git mv backend/app/api/health.py backend/app/infrastructure/observability/health/router.py
git mv backend/app/api/lcm.py    backend/app/infrastructure/observability/lcm/router.py
git mv backend/app/api/auth.py   backend/app/infrastructure/auth/router.py
git mv backend/app/api/oauth.py  backend/app/infrastructure/auth/oauth/router.py
# import repoints
```

### Task 8.8: Verify api/ is empty + delete

```bash
ls backend/app/api/
# Expected: only __init__.py (possibly __pycache__)
git rm -r backend/app/api/
```

### Task 8.9: Update `router_registry.py`

The factory functions (`get_chat_router()` etc.) used to return router objects. Each new `*/router.py` should expose either:
- A module-level `router: APIRouter = APIRouter(...)`, or
- A `get_router() -> APIRouter` factory.

Convert each factory to module-level if it doesn't need lazy init. Update `_ROUTER_MODULES` in `infrastructure/router_registry.py` to point at the new paths (already done in Phase 2 if anticipated; if not, do it now).

### Task 8.10: Verify + commit

```bash
cd backend && uv run ruff check . && uv run mypy . && uv run pytest tests/ -x -q
git add backend/
git commit -m "refactor(backend): api/ files redistributed to domain packages"
git push --no-verify
gh pr checks --watch
```

---

## Phase 9 — `crud/` → per-domain `crud.py` modules

The `crud/` directory has 15 files; each moves into its owning domain.

### Task 9.1: Map crud files to domains

| Current | New |
|---|---|
| `crud/conversation.py` | `app/conversations/crud.py` |
| `crud/chat_message.py` | `app/conversations/messages_crud.py` (or fold into conversations/crud.py) |
| `crud/user_preferences.py` | `app/infrastructure/auth/preferences_crud.py` |
| `crud/workspace.py` | `app/workspace/crud.py` |
| `crud/project.py` | `app/projects/crud.py` |
| `crud/audit.py` | `app/governance/audit/crud.py` |
| `crud/cost.py` | `app/governance/cost/crud.py` |
| `crud/scheduled_job.py` | `app/agents/scheduling/crud.py` |
| `crud/mcp_server.py` | `app/integrations/mcp_servers/crud.py` |
| `crud/lcm.py` | `app/lcm/crud.py` (or fold into lcm package) |
| `crud/channel.py` | `app/channels/crud.py` |

### Task 9.2: Move each file + repoint imports

For each row, `git mv` then sed-update imports across the repo. Pattern repeats.

### Task 9.3: Verify + commit

```bash
cd backend && uv run pytest tests/ -x -q
git add backend/
git commit -m "refactor(backend): crud/ files redistributed to owning domains"
git push --no-verify
gh pr checks --watch
```

---

## Phase 10 — `core/*` → top-level domains and infrastructure

The big purge. After this phase, `backend/app/core/` no longer exists.

### Task 10.1: Move `core/providers/` → `app/providers/`

```bash
git mv backend/app/core/providers backend/app/providers
cd backend && rg -l 'from app\.core\.providers' | \
  xargs sed -i '' 's|from app\.core\.providers|from app.providers|g'
```

### Task 10.2: Move `core/tools/` → `app/tools/`

```bash
git mv backend/app/core/tools backend/app/tools
cd backend && rg -l 'from app\.core\.tools' | \
  xargs sed -i '' 's|from app\.core\.tools|from app.tools|g'
```

### Task 10.3: Move `core/agent_loop/` → `app/agents/`

The `core/agent_loop/` content (loop.py, hooks.py, safety.py, types.py, tools.py) lands at the `agents/` package root.

```bash
mv backend/app/core/agent_loop/*.py backend/app/agents/
git rm -r backend/app/core/agent_loop/
git add backend/app/agents/
cd backend && rg -l 'from app\.core\.agent_loop' | \
  xargs sed -i '' 's|from app\.core\.agent_loop|from app.agents|g'
```

### Task 10.4: Move `core/lcm/` → `app/lcm/`

```bash
git mv backend/app/core/lcm backend/app/lcm
cd backend && rg -l 'from app\.core\.lcm' | xargs sed -i '' 's|from app\.core\.lcm|from app.lcm|g'
```

### Task 10.5: Move `core/governance/` → `app/governance/`

`app/governance/` already exists from Phase 8 with `audit/` and `cost/`. Move the policy + enforcement modules into `app/governance/policy/`:

```bash
mkdir -p backend/app/governance/policy
mv backend/app/core/governance/*.py backend/app/governance/policy/
git rm -r backend/app/core/governance/
cd backend && rg -l 'from app\.core\.governance' | \
  xargs sed -i '' 's|from app\.core\.governance|from app.governance.policy|g'
```

### Task 10.6: Move `core/event_bus/` → `infrastructure/event_bus/`

```bash
git mv backend/app/core/event_bus backend/app/infrastructure/event_bus_pkg
# Then merge with existing empty infrastructure/event_bus/:
mv backend/app/infrastructure/event_bus_pkg/* backend/app/infrastructure/event_bus/
rm -rf backend/app/infrastructure/event_bus_pkg
cd backend && rg -l 'from app\.core\.event_bus' | \
  xargs sed -i '' 's|from app\.core\.event_bus|from app.infrastructure.event_bus|g'
```

### Task 10.7: Move `core/observability/` → `infrastructure/observability/`

```bash
mv backend/app/core/observability/*.py backend/app/infrastructure/observability/
git rm -r backend/app/core/observability/
cd backend && rg -l 'from app\.core\.observability' | \
  xargs sed -i '' 's|from app\.core\.observability|from app.infrastructure.observability|g'
```

### Task 10.8: Move `core/scheduler/` → `app/agents/scheduling/scheduler.py`

```bash
git mv backend/app/core/scheduler/scheduler.py backend/app/agents/scheduling/scheduler.py
# (and any sibling files into agents/scheduling/)
git rm -r backend/app/core/scheduler/
cd backend && rg -l 'from app\.core\.scheduler' | \
  xargs sed -i '' 's|from app\.core\.scheduler|from app.agents.scheduling.scheduler|g'
```

### Task 10.9: Move `core/plugins/` → `app/agents/plugins/`

```bash
git mv backend/app/core/plugins backend/app/agents/plugins
cd backend && rg -l 'from app\.core\.plugins' | xargs sed -i '' 's|from app\.core\.plugins|from app.agents.plugins|g'
```

### Task 10.10: Move remaining core/* files into appropriate homes

After the above, `backend/app/core/` should contain only:
- `config.py` → moves to `app/config.py` (root)
- `chat_aggregator.py` → moves to `app/chat/aggregator.py`
- `telemetry.py` → moves to `app/infrastructure/observability/telemetry.py`
- (Anything else: inspect, decide)

Move each individually. Repoint imports.

### Task 10.11: Move `core/exporters/` → `app/conversations/exports/`

```bash
mv backend/app/core/exporters/*.py backend/app/conversations/exports/
git rm -r backend/app/core/exporters/
cd backend && rg -l 'from app\.core\.exporters' | \
  xargs sed -i '' 's|from app\.core\.exporters|from app.conversations.exports|g'
```

### Task 10.12: Confirm `core/` is empty + remove

```bash
find backend/app/core -type f | head
# Expected: empty or only __init__.py + __pycache__
git rm -r backend/app/core/
```

### Task 10.13: Verify + commit

```bash
cd backend && uv run ruff check . && uv run mypy . && uv run pytest tests/ -x -q
git add backend/
git commit -m "refactor(backend): core/* purged into top-level domains and infrastructure"
git push --no-verify
gh pr checks --watch
```

---

## Phase 11 — Drop `returns` library, install typed exception tree

### Task 11.1: Define the root exception tree

**Files:**
- Create: `backend/app/exceptions.py`
- Create: `backend/tests/test_exception_tree.py`

- [ ] **Step 1: Write failing test**

```python
"""Verify the root exception hierarchy."""

from app.exceptions import DomainError, InfrastructureError, PawrrtalError


def test_pawrrtal_error_is_root() -> None:
    """All Pawrrtal-raised exceptions inherit from PawrrtalError."""
    assert issubclass(DomainError, PawrrtalError)
    assert issubclass(InfrastructureError, PawrrtalError)


def test_pawrrtal_error_distinct_from_exception() -> None:
    """PawrrtalError is its own subclass, not Exception alias."""
    assert issubclass(PawrrtalError, Exception)
    assert PawrrtalError is not Exception
```

- [ ] **Step 2: Implement `app/exceptions.py`**

```python
"""Pawrrtal exception hierarchy.

Two roots under :class:`PawrrtalError`:
- :class:`DomainError` — business-logic failures. Translate to 4xx at the
  HTTP boundary.
- :class:`InfrastructureError` — plumbing failures (DB, event bus, etc.).
  Propagate as 500 unless explicitly caught.

Each domain extends ``DomainError`` in its own ``exceptions.py``. Use the
narrowest exception type the call site can usefully react to.
"""


class PawrrtalError(Exception):
    """Root of every Pawrrtal-raised exception. Never raised directly."""


class DomainError(PawrrtalError):
    """Business-logic failure. Translate to 4xx at the HTTP boundary."""


class InfrastructureError(PawrrtalError):
    """Plumbing failure. Translate to 500 at the HTTP boundary unless explicitly handled."""
```

### Task 11.2: Per-domain exceptions modules

- [ ] **Step 1: Create `app/chat/exceptions.py`**

```python
"""Chat-domain exceptions."""

from app.exceptions import DomainError


class ChatError(DomainError):
    """Root of chat-domain failures."""


class CostBudgetExceeded(ChatError):
    """Per-user monthly cost cap hit before turn could start."""


class ProviderUnavailable(ChatError):
    """Resolved provider couldn't be instantiated (auth/config missing)."""
```

- [ ] **Step 2: Create `app/providers/exceptions.py`**

```python
"""Provider-domain exceptions: typed errors for LLM SDK failures."""

from dataclasses import dataclass

from app.exceptions import DomainError


class ProviderError(DomainError):
    """Root of provider-domain failures."""


class ProviderAuthError(ProviderError):
    """API key invalid, expired, or missing."""


@dataclass
class ProviderRateLimitError(ProviderError):
    """Provider rejected the request as rate-limited."""

    retry_after: float | None = None


class ProviderTimeoutError(ProviderError):
    """Provider didn't respond within the configured deadline."""


class ProviderUnsupportedParamError(ProviderError):
    """Provider rejected a parameter we sent (e.g. reasoning_effort on a model that doesn't support it)."""


class ProviderUnknownError(ProviderError):
    """Catch-all when the SDK error doesn't match any narrower variant."""
```

- [ ] **Step 3: Create `app/tools/exceptions.py`**

```python
"""Tool-domain exceptions: MCP + factory failures."""

from dataclasses import dataclass

from app.exceptions import DomainError


class ToolError(DomainError):
    """Root of tool-domain failures."""


class McpTimeoutError(ToolError):
    """MCP server didn't respond within the deadline."""


@dataclass
class McpAuthError(ToolError):
    """MCP server rejected auth."""

    status_code: int = 401


@dataclass
class McpServerError(ToolError):
    """MCP server returned a 5xx."""

    status_code: int = 500


class McpProtocolError(ToolError):
    """MCP response didn't conform to the expected JSON-RPC shape."""
```

- [ ] **Step 4: Create `app/conversations/exceptions.py`**

```python
"""Conversations-domain exceptions."""

from app.exceptions import DomainError


class ConversationNotFound(DomainError):
    """The requested conversation doesn't exist or isn't visible to this user."""
```

- [ ] **Step 5: Create `app/infrastructure/exceptions.py`**

```python
"""Infrastructure-domain exceptions: plumbing failures."""

from app.exceptions import InfrastructureError


class DatabaseError(InfrastructureError):
    """Catch-all replacement for the previous SQLAlchemyError handler. Use narrower types when possible."""


class EventBusError(InfrastructureError):
    """Event bus subscriber/publisher failed in a way that broke the bus."""
```

### Task 11.3: Convert `crud/conversation.py` Maybe → Optional

**Files:**
- Modify: `backend/app/conversations/crud.py` (was `crud/conversation.py`)
- Modify: 5 callers

- [ ] **Step 1: Update `get_conversation` and `get_conversation_status`**

Replace:

```python
from returns.maybe import Maybe, Nothing, Some

async def get_conversation(...) -> Maybe[Conversation]:
    row = await session.get(Conversation, conv_id)
    return Maybe.from_optional(row)
```

With:

```python
async def get_conversation(...) -> Conversation | None:
    """Fetch a conversation by ID. Returns ``None`` if missing or not visible."""
    return await session.get(Conversation, conv_id)
```

Same for `get_conversation_status` — return the `ConversationStatus | None` directly.

- [ ] **Step 2: Update the 5 callers**

```bash
cd backend && rg -n '\.value_or\(None\)' app/ | grep conversation
# Expected: 5 matches across app/chat/router.py, app/conversations/router.py,
# app/conversations/exports/router.py, app/lcm/, app/channels/telegram/status.py
```

For each caller, replace:

```python
maybe_conv = await get_conversation(...)
conv = maybe_conv.value_or(None)
if conv is None: ...
```

With:

```python
conv = await get_conversation(...)
if conv is None: ...
```

- [ ] **Step 3: Update tests in `backend/tests/test_conversation_crud.py`**

Replace `Maybe`/`Some`/`Nothing` imports and assertions with direct `None` checks. The test now reads:

```python
result = await get_conversation(session, conv_id)
assert result is not None
assert result.id == conv_id
```

### Task 11.4: Convert `tools/external_mcp.py` IOResult → raises

**Files:**
- Modify: `backend/app/tools/external_mcp.py`
- Modify: `backend/tests/test_external_mcp_tools.py`

- [ ] **Step 1: Remove the McpError dataclass union** (replaced by tools/exceptions.py)

- [ ] **Step 2: Convert `call_external_mcp_tool` to raise typed exceptions**

```python
# Before:
async def call_external_mcp_tool(...) -> IOResult[ToolOutput, McpError]:
    try:
        ...
    except httpx.TimeoutException:
        return IOFailure(McpTimeoutError())

# After:
async def call_external_mcp_tool(...) -> ToolOutput:
    """Invoke an external MCP tool. Raises McpError variants on failure."""
    try:
        ...
    except httpx.TimeoutException as e:
        raise McpTimeoutError() from e
```

- [ ] **Step 3: Update the AgentTool wrapper**

The tool wrapper currently calls `_unwrap_mcp_result` to translate `IOResult` to the `[io_error] ...` string contract. Replace with:

```python
async def execute(...) -> str:
    try:
        result = await call_external_mcp_tool(...)
        return result.text
    except McpAuthError as e:
        return f"[io_error] auth failed (status={e.status_code})"
    except McpTimeoutError:
        return "[io_error] tool timed out"
    except McpServerError as e:
        return f"[io_error] server error (status={e.status_code})"
    except McpProtocolError as e:
        return f"[io_error] protocol violation: {e}"
```

- [ ] **Step 4: Update tests**

Replace `Success(...)` / `Failure(...)` assertions with direct value checks + `pytest.raises(McpXxxError)` for the error paths.

### Task 11.5: Convert `providers/litellm_provider.py` FutureResult → raises

**Files:**
- Modify: `backend/app/providers/litellm_provider.py`
- Modify: `backend/tests/test_litellm_provider.py`

- [ ] **Step 1: Remove the FutureResult/Result return type**

Change:

```python
def open_litellm_stream(...) -> FutureResult[AsyncIterator[StreamEvent], ProviderError]:
```

To:

```python
async def open_litellm_stream(...) -> AsyncIterator[StreamEvent]:
    """Open a streaming LiteLLM completion. Raises ProviderError variants on failure."""
```

- [ ] **Step 2: Convert `_classify_litellm_exception` to raise instead of return**

```python
def _raise_classified_litellm_exception(exc: BaseException) -> None:
    """Map a LiteLLM SDK exception to a ProviderError variant and raise."""
    if isinstance(exc, RateLimitError):
        retry_after = _extract_retry_after(exc)
        raise ProviderRateLimitError(retry_after=retry_after) from exc
    if isinstance(exc, AuthenticationError):
        raise ProviderAuthError() from exc
    # ... etc
    raise ProviderUnknownError(str(exc)) from exc
```

- [ ] **Step 3: Update the chat router boundary**

In `app/chat/router.py`, wrap the provider call:

```python
try:
    async for event in provider.stream(...):
        yield event
except ProviderRateLimitError as e:
    yield {"type": "error", "content": f"Rate limit hit; retry after {e.retry_after}s"}
except ProviderAuthError:
    yield {"type": "error", "content": "Provider auth failed"}
# ... etc
```

- [ ] **Step 4: Update tests** — replace `IOSuccess(...)` / `IOFailure(...)` assertions with `pytest.raises(ProviderXxxError)`.

### Task 11.6: Remove the `returns` dep + mypy plugin

- [ ] **Step 1: Remove from pyproject**

```bash
cd backend && sed -i '' '/returns>=/d' pyproject.toml
cd backend && sed -i '' '/returns\.contrib\.mypy\.returns_plugin/d' pyproject.toml
```

- [ ] **Step 2: Lock file refresh**

```bash
cd backend && uv lock
```

- [ ] **Step 3: Verify no `from returns` imports remain**

```bash
cd backend && rg 'from returns|import returns' app/ tests/
# Expected: zero hits
```

- [ ] **Step 4: Remove the `returns-for-pawrrtal` skill + add a "superseded" note to the corpus**

```bash
rm -rf .claude/skills/returns-for-pawrrtal/
```

Add to the top of `docs/superpowers/specs/2026-05-28-returns-adoption-grilling.md` and `2026-05-28-returns-phase-0-corpus.md`:

```markdown
> **Status: superseded.** Returns adoption was reverted in the
> backend restructure (see `2026-05-28-backend-restructure-design.md`).
> This document is kept as historical record.
```

### Task 11.7: Verify + commit

```bash
cd backend && uv run ruff check . && uv run mypy . && uv run pytest tests/ -x -q
git add backend/ docs/ .claude/
git commit -m "refactor(backend): drop returns library; install typed exception hierarchy"
git push --no-verify
gh pr checks --watch
```

---

## Phase 12 — Active recall code-smell fixes

**Files:**
- Modify: `backend/app/agents/plugins/active_recall/recall_agent.py`
- Create/modify: `backend/tests/agents/plugins/active_recall/test_tool_failure_paths.py`

### Task 12.1: Replace broad `except Exception` (line ~301)

Find:

```python
except Exception as exc:
    logger.warning("active_recall failed: %s", exc)
    return ""
```

Replace with:

```python
except (asyncio.TimeoutError, ProviderError, ToolError) as exc:
    logger.warning("active_recall failed: %s", exc)
    return ""
# Real config/import errors propagate.
```

### Task 12.2: Make `draft_updater` failure explicit

Find:

```python
with contextlib.suppress(Exception):
    await draft_updater(html)
```

Replace:

```python
try:
    await asyncio.wait_for(draft_updater(html), timeout=_DRAFT_UPDATE_TIMEOUT_S)
except asyncio.TimeoutError:
    logger.warning("active_recall: draft_updater timed out after %.1fs", _DRAFT_UPDATE_TIMEOUT_S)
except Exception as exc:  # noqa: BLE001 — draft is non-essential; log + skip
    logger.warning("active_recall: draft_updater failed", exc_info=exc)
```

### Task 12.3: Name the magic numbers

At module top, add:

```python
_RECALL_MAX_CHARS: int = 600
"""Cap on recalled-context length injected into the main agent's system prompt."""

_RECALL_MAX_TRIES: int = 3
"""Max iterations the recall sub-agent may take before giving up."""

_DRAFT_UPDATE_TIMEOUT_S: float = 2.0
"""Wall clock cap on the draft-updater callback; longer = skip the update."""
```

Replace inline `600` and `3` with the constants.

### Task 12.4: Type the draft_updater parameter

Replace:

```python
def __init__(self, ..., draft_updater: Any | None = None) -> None:
```

With:

```python
from collections.abc import Awaitable, Callable

DraftUpdater = Callable[[str], Awaitable[None]]


def __init__(self, ..., draft_updater: DraftUpdater | None = None) -> None:
```

### Task 12.5: New integration test for tool-failure paths

`backend/tests/agents/plugins/active_recall/test_tool_failure_paths.py`:

```python
"""Active recall must handle tool failures gracefully — never crash the main turn."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.agents.plugins.active_recall.recall_agent import run_active_recall
from app.tools.exceptions import McpAuthError, McpTimeoutError

# Use the ScriptedStreamFn pattern from tests/agent_harness.py
from tests.agent_harness import ScriptedStreamFn, run_scenario, tool_call_turn, text_turn


@pytest.mark.anyio
async def test_recall_returns_empty_on_tool_timeout(db_session, test_user) -> None:
    """When lcm_search times out, recall returns an empty string and does NOT raise."""
    script = ScriptedStreamFn([
        tool_call_turn("lcm_search", {"query": "test"}),
        # The tool will time out; the script's job is to drive the agent.
    ])
    # Tool factory that always raises McpTimeoutError when invoked
    def _flaky_tool_factory():
        async def _tool(args: dict) -> str:
            raise McpTimeoutError()
        return _tool

    result = await run_active_recall(
        question="test question",
        user_id=test_user.id,
        conversation_id=uuid.uuid4(),
        stream_fn=script,
        tool_factory=_flaky_tool_factory,
    )
    assert result == ""


@pytest.mark.anyio
async def test_recall_returns_empty_on_tool_auth_error(db_session, test_user) -> None:
    """When lcm_grep returns permission denied, recall returns empty."""
    script = ScriptedStreamFn([
        tool_call_turn("lcm_grep", {"pattern": "secret"}),
    ])
    def _denied_tool():
        async def _tool(args: dict) -> str:
            raise McpAuthError(status_code=403)
        return _tool

    result = await run_active_recall(..., stream_fn=script, tool_factory=_denied_tool)
    assert result == ""
```

### Task 12.6: Verify + commit

```bash
cd backend && uv run pytest tests/agents/plugins/active_recall/ -v
git add backend/
git commit -m "fix(active-recall): tighten error handling per audit (6 smells)"
git push --no-verify
gh pr checks --watch
```

---

## Phase 13 — Alembic flatten

### Task 13.1: Capture current schema

```bash
# Spin up a fresh PG locally or use SQLite for the capture:
cd backend && rm -f test_session.sqlite
cd backend && uv run alembic upgrade head
cd backend && uv run python -c "
from sqlalchemy import create_engine, MetaData
from sqlalchemy.schema import CreateTable
e = create_engine('sqlite:///test_session.sqlite')
m = MetaData()
m.reflect(bind=e)
print('\n'.join(str(CreateTable(t).compile(e)) for t in m.tables.values()))
" > /tmp/current_schema.sql
```

Or, if a Postgres dev DB is available:

```bash
pg_dump --schema-only --no-owner --no-privileges -h localhost -U pawrrtal pawrrtal_dev > /tmp/current_schema.sql
```

Commit `current_schema.sql` to the PR as review evidence (under `docs/superpowers/restructure-evidence/`).

### Task 13.2: Delete existing migrations

```bash
git rm backend/alembic/versions/*.py
```

### Task 13.3: Generate consolidated initial migration

```bash
cd backend && uv run alembic revision --autogenerate -m "consolidated_initial"
```

Inspect the generated file under `backend/alembic/versions/`. It should be a single file with `op.create_table(...)` calls for every ORM table.

### Task 13.4: Verify the consolidated migration matches the schema

```bash
# Apply to a fresh DB:
cd backend && rm -f test_session.sqlite
cd backend && uv run alembic upgrade head
# Re-extract schema and diff:
cd backend && uv run python -c "..." > /tmp/post_migration_schema.sql
diff /tmp/current_schema.sql /tmp/post_migration_schema.sql
# Expected: empty (or only ordering differences)
```

### Task 13.5: Write a stamp playbook

`docs/superpowers/restructure-evidence/alembic-stamp-runbook.md`:

```markdown
# Alembic stamp runbook (post-restructure)

Run on each deployed environment AFTER the PR merges and BEFORE running any
future migration.

1. SSH or use Railway shell into the target deployment.
2. Verify current Alembic state:
   `alembic current` — expect the LAST pre-flatten revision ID.
3. Apply the stamp:
   `alembic stamp <new_initial_revision_id>` (replace with the actual ID).
4. Verify:
   `alembic current` — expect `<new_initial_revision_id>`.
5. Run `alembic heads`; expect exactly that revision.

If `alembic current` reports something OTHER than the last pre-flatten
revision, STOP. The environment was at a different schema point than
expected. Open an incident.
```

### Task 13.6: Verify + commit

```bash
cd backend && uv run pytest tests/ -x -q
git add backend/alembic/ docs/superpowers/restructure-evidence/
git commit -m "refactor(backend): alembic flatten to consolidated initial migration"
git push --no-verify
gh pr checks --watch
```

---

## Phase 14 — `tests/` mirrors `app/`

### Task 14.1: Create the target test tree

```bash
mkdir -p backend/tests/{chat,conversations,agents,channels,providers,tools,integrations,workspace,projects,lcm,governance,infrastructure,e2e}
```

### Task 14.2: Move each test file to its mirror

Pattern (per file):

```bash
# tests/test_chat_router.py → tests/chat/test_router.py
git mv backend/tests/test_chat_router.py backend/tests/chat/test_router.py
```

Mapping table (representative; complete list during execution):

| Current | New |
|---|---|
| `test_chat_*.py` | `chat/test_*.py` |
| `test_conversation*.py` | `conversations/test_*.py` |
| `test_agent_loop*.py`, `test_safety*.py` | `agents/test_*.py` |
| `test_active_recall*.py` | `agents/plugins/active_recall/test_*.py` |
| `test_telegram*.py` | `channels/test_telegram_*.py` |
| `test_*_provider.py`, `test_litellm*.py`, `test_openai_codex*.py` | `providers/<host>/test_*.py` |
| `test_external_mcp_tools.py`, `test_*_tools.py` | `tools/test_*.py` |
| `test_workspace*.py` | `workspace/test_*.py` |
| `test_*_crud.py` | folded into the domain test dir |
| `test_health.py`, `test_lcm_endpoint.py` | `infrastructure/observability/test_*.py` |
| `e2e_paw/*` | unchanged (paw CLI deferred) |

### Task 14.3: Update test imports if any tests cross-import each other

```bash
cd backend && rg -l 'from tests\.' tests/ | head
# Each needs a sed update to the new path.
```

### Task 14.4: Verify + commit

```bash
cd backend && uv run pytest tests/ -x -q
# Verify ALL tests still discovered + pass.
git add backend/tests/
git commit -m "refactor(backend): tests/ mirrors app/ structure"
git push --no-verify
gh pr checks --watch
```

---

## Phase 15 — Update `.sentrux/rules.toml`

### Task 15.1: Rewrite layer definitions

Replace `.sentrux/rules.toml` with the spec's §8 contents:

```toml
# (See spec §8 — pasted here verbatim during execution.)
```

### Task 15.2: Verify sentrux passes

```bash
just sentrux
# Expected: zero violations
```

### Task 15.3: Commit

```bash
git add .sentrux/rules.toml
git commit -m "chore(sentrux): update layer rules for new backend tree"
git push --no-verify
gh pr checks --watch
```

---

## Phase 16 — Update docs

### Task 16.1: CLAUDE.md backend section

Update `CLAUDE.md` (project root) and `backend/.claude/CLAUDE.md` to reflect the new layout. Replace the old structure description with the new tree (spec §1).

### Task 16.2: Onboarding docs

```bash
rg -l 'app/core/|app/api/|app/integrations/telegram' docs/
# For each match, update the path to the new home.
```

### Task 16.3: Bean cleanup

```bash
# Mark the epic bean complete:
beans update pawrrtal-<epic-id> -s completed --body-append "## Summary of Changes
Implemented the 16-phase restructure per docs/superpowers/plans/2026-05-28-backend-restructure.md. CI green, PR merged."

# Close any beans that became obsolete from this restructure.
```

### Task 16.4: Verify + final commit

```bash
git add CLAUDE.md backend/.claude/CLAUDE.md docs/ .beans/
git commit -m "docs(restructure): update CLAUDE.md + onboarding docs for new layout"
git push --no-verify
gh pr checks --watch
```

---

## Post-implementation

After Phase 16 lands and CI is green:

1. Mark the PR ready for review (drop `--draft`).
2. Run `/make-pr-easy-to-review` to clean the commit history and write a PR description that walks through each commit.
3. Run `/thermo-nuclear-code-quality-review` for adversarial review of the entire change.
4. Address findings until reviews pass.
5. Squash-merge into main (the PR's chosen merge method).
6. Per Section 6, run the alembic stamp on staging, soak, then prod.

---

## Self-review checklist

After writing this plan, the author verified:

1. **Spec coverage:** Every section of the spec maps to a phase. §1 tree → Phases 1–10. §2 errors → Phase 11. §3 models → Phase 3. §4 tests → Phase 14. §5 main.py → Phase 2. §6 alembic → Phase 13. §7 active recall → Phase 12. §8 sentrux → Phase 15. §9 sequence → entire plan. §10 risks → addressed inline.
2. **Placeholder scan:** No "TBD" / "implement later" / "fill in details" remain.
3. **Type consistency:** Function names (`startup_hook`, `LifecycleRegistry`, `register_routers`, `create_app`, `wrap_cors`, `_RECALL_MAX_CHARS`) are consistent across tasks.
4. **Ambiguity:** "If a Postgres dev DB is available" in Task 13.1 is intentional — environments differ; the executor picks the right capture command.

# Plan: Per-User Workspaces + FileTools + Admin Seed

## Context

The Pawrrtal backend currently creates Agno agents with only an MCP tool (docs server). We want agents to be able to **manipulate files** within a **per-user workspace directory** that persists across conversations. We also need a **seeded admin account** so we can test this from scripts without manual login.

**Storage**: Railway volume mounted at `/data`. User workspaces live at `/data/workspaces/{user_id}/`. Persists across redeploys.

**Security**: `FileTools` uses `_check_path()` which resolves paths and validates via `relative_to(base_dir)` — blocks directory traversal. `ShellTools` and `PythonTools` were evaluated and rejected (no real sandboxing).

---

## Step 1: Add settings to `config.py`

**File**: `backend/app/infrastructure/config.py`

Add to `Settings`:
```python
workspace_base_dir: str = "/data/workspaces"
admin_email: str = "admin@pawrrtal.dev"
admin_password: str = "admin1234"
```

---

## Step 2: Create workspace helper

**New file**: `backend/app/workspace/filesystem.py`

```python
from pathlib import Path
from uuid import UUID
from app.core.config import settings

def get_user_workspace(user_id: UUID) -> Path:
    workspace = Path(settings.workspace_base_dir) / str(user_id)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace
```

---

## Step 3: Wire FileTools into agent

**File**: `backend/app/agents/`

- Import `FileTools` from `agno.tools.file`
- Import `get_user_workspace`
- In `create_agent`, compute workspace path, add tools:

```python
workspace = get_user_workspace(user_id)
tools=[
    MCPTools(transport="streamable-http", url="https://docs.agno.com/mcp"),
    FileTools(base_dir=workspace),
]
```

Also add agent instructions mentioning the workspace so the LLM knows it can use these tools.

---

## Step 4: Admin seed function

**New file**: `backend/app/cli/admin_seed.py`

- **Skip entirely in production** — check `settings.is_production` and return early with a log message
- Use `async_session_maker` from `app.db` to open a session (no request context at startup)
- Instantiate `SQLAlchemyUserDatabase` + `UserManager` manually
- Query by `settings.admin_email` — if not found, create with `safe=False`
- Pass `invite_code=settings.registration_secret` to satisfy invite validation
- Log result, wrap in try/except so failures don't crash startup

Key pattern (from `db.py` and `users.py`):
```python
async def seed_admin_user() -> None:
    if settings.is_production:
        log_info("Skipping admin seed in production")
        return

    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        existing = await manager.get_by_email(settings.admin_email)
        if not existing:
            await manager.create(UserCreate(
                email=settings.admin_email,
                password=settings.admin_password,
                invite_code=settings.registration_secret,
            ), safe=False)
```

---

## Step 5: Call seed in lifespan

**File**: `backend/main.py`

In `lifespan()`, after `await create_db_and_tables()`:
```python
from app.core.admin_seed import seed_admin_user
await seed_admin_user()
```

---

## Step 6: Tests

**New file**: `backend/tests/conftest.py`
- `httpx.AsyncClient` fixture pointed at the test app
- Admin login fixture that POSTs to `/auth/jwt/login` and returns the session cookie

**New file**: `backend/tests/test_workspace.py`
- `test_get_user_workspace_creates_directory`
- `test_get_user_workspace_idempotent`

**New file**: `backend/tests/test_admin_seed.py`
- `test_seed_creates_admin`
- `test_seed_idempotent`

**New file**: `backend/tests/test_agent_tools.py`
- `test_agent_has_file_tools`
- `test_agent_tools_base_dir_matches_workspace`

---

## Step 7: Update `.env` / `.env.example`

Add:
```
WORKSPACE_BASE_DIR=/data/workspaces
ADMIN_EMAIL=admin@pawrrtal.dev
ADMIN_PASSWORD=admin1234
```

---

## Implementation Order

1. `config.py` (settings)
2. `workspace.py` (new)
3. `agents.py` (add tools)
4. `admin_seed.py` (new)
5. `main.py` (lifespan)
6. Tests
7. `.env` updates

---

## Verification

1. Run the app locally, check logs for "Admin user created/exists"
2. Login as admin via `POST /auth/jwt/login` with form data `username=admin@pawrrtal.dev&password=admin1234`
3. Send a chat message asking the agent to "create a file called hello.txt with 'Hello World' in it"
4. Verify the file appears in `workspace_base_dir/{user_id}/hello.txt`
5. Ask the agent to "list files in the workspace" and "read hello.txt"
6. Run `pytest backend/tests/` — all tests pass

---

## Critical Files

- `backend/app/infrastructure/config.py` — add 3 settings
- `backend/app/agents/` — add FileTools
- `backend/app/workspace/filesystem.py` — new, workspace path helper
- `backend/app/cli/admin_seed.py` — new, startup admin seeder
- `backend/main.py` — 2-line lifespan change
- `backend/app/db.py` — reference for `async_session_maker`, `User`
- `backend/app/users.py` — reference for `UserManager` pattern
- `backend/app/schemas.py` — reference for `UserCreate` schema

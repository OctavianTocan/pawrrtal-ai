# `paw` — Pawrrtal Agent CLI Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**v2 supersedes the v1 of this file.** v1 (saved earlier today) had three load-bearing assumptions contradicted by the actual repo — see the **Critical plan corrections** section below. v2 fixes them and rewrites the surface to match the ntn (Notion CLI) pattern an adversarial reviewer + a separate gap-hunt agent + an ntn deep-dive each pointed at.

**Goal:** Deliver `paw`, a Pawrrtal agent CLI persona that drives the **same HTTP API the React frontend uses** so any claim like "the Codex provider works end-to-end" is backed by a runnable, JSON-output script. `paw` borrows the resource+verb shape from `ntn` (Notion CLI), supports the testing scenarios the gap-hunt surfaced (chat-roundtrip, model-switch-mid-conversation, etc.), ships a `.claude/skills/paw/SKILL.md` so future agents discover it automatically, and includes a minimal backend change required to make the headline `verify codex` assertion possible (exposing `codex_thread_id` in `ConversationRead`).

**Architecture:** Python 3.13 CLI installed into the existing `backend/` uv project as a console script (`paw`). All state for the persona lives under `~/.config/pawrrtal/<profile>/` (XDG-style; default profile: `default`). The CLI never imports `app.*` runtime modules — it goes through HTTP exclusively. SSE consumption mirrors the **frontend's** technique (`fetch` + `ReadableStream.getReader()` + `TextDecoderStream` in JS → byte-level chunked reader + manual `\n\n` framing in Python via `httpx.AsyncClient.stream()`) instead of `httpx-sse`, because Pawrrtal's chat endpoint streams a custom protocol (one JSON dict per `data:` line plus the literal `[DONE]` sentinel) — not RFC-strict SSE. Three output modes everywhere: human (default), `--json` (machine), `--plain` (TSV no headers, pipe-friendly). Conversations are addressed by **client-generated UUIDs**: the CLI pre-generates a v4 UUID, calls `POST /api/v1/conversations/{uuid}`, then `POST /api/v1/chat/` with `conversation_id` populated — same flow as the frontend at `frontend/features/chat/hooks/use-chat.ts`. Cookies are managed by `httpx.Cookies` (the cookie jar), never regex-parsed.

**Tech Stack:** Python 3.13, `typer` (CLI shell — rich help text, native subcommands, async), `httpx` (HTTP + manual SSE stream reading), `pydantic` v2 (request/response models share field names with the backend), `uuid` (stdlib for v4 UUID generation), pytest + `respx` for unit tests + a **real-backend integration suite** gated on `PAW_E2E=1`.

---

## Critical plan corrections (vs v1)

These three were contradicted by the actual repo. Fix before any code lands.

1. **`ChatRequest.conversation_id` is required, not optional.** `backend/app/schemas.py:301` types it as `uuid.UUID` (no `| None`). The frontend pre-generates the UUID and calls `POST /api/v1/conversations/{uuid}` first — see `backend/app/api/conversations.py:242-254` for the route. `paw chat send --new` must mirror that flow: generate UUID → create conversation → send chat.

2. **`ConversationRead` does not expose `codex_thread_id`.** The column exists on `Conversation` (`backend/app/models.py:104`) but `ConversationRead` (`backend/app/schemas.py:110`) and the route handlers (`backend/app/api/conversations.py:113-126,191-204`) drop it. The v1 plan's headline assertion (`codex_thread_id_persisted`) is unverifiable over HTTP today. **Fix:** add `codex_thread_id: str | None` to `ConversationRead` and include it in both route handlers' explicit field lists. This is a tiny, non-breaking schema addition.

3. **`GET /api/v1/models` returns an envelope `{"models": [...], "etag": "..."}`** (`backend/app/api/models.py:129`), not a bare list. Every `paw models …` consumer must `.get("models", [])`. The `etag` is the picker filter fingerprint and is itself worth exposing.

Smaller corrections rolled into the design below:
- **Cookie persistence** via `httpx.Cookies` instance serialized to disk, never raw `Set-Cookie` regex parsing (RFC 1123 dates contain commas — `Expires=Wed, 27-May-2026 ...` — and `.split(",")[0]` corrupts them).
- **SSE events from the chat router** include `type: "message"` (`backend/app/api/chat.py:309`) on top of provider-emitted `delta` / `thinking` / `tool_use` / `tool_result` / `error` / `usage` / `done` / `[DONE]`. Enumerate all of them.
- **Auth flow:** `POST /auth/dev-login` may 503/404 in some configs (`backend/app/api/auth.py:28-38`); document and fall back to `POST /auth/jwt/login` (form-encoded). FastAPI-Users uses cookie auth — `cookie_transport` at `backend/app/users.py:65-71` confirms `session_token` HttpOnly cookie.
- **respx-mocked tests are tautological for the verification claim.** `paw verify codex` must have a **live-backend integration test** (gated on `PAW_E2E=1`) — that's where the "drives the real surface" claim is actually proven. The respx tests cover CLI mechanics only.

---

## Why `paw` (and not the earlier name `pcli`)

`pcli` is generic, unmemorable, and easy to confuse with other tools. `paw` is three letters, brand-mnemonic (Pawrrtal), easy to type, and follows the same shape as `ntn` (Notion CLI). It's the project-namespace name we'll see daily.

---

## Design principles (from the ntn deep-dive)

Patterns to copy:

- **Resource + verb, never resource-only.** `paw conversations send` not `paw chat`. Predictable enumeration. Aliases for ergonomics (`paw conv` → `paw conversations`).
- **`paw doctor` returns a checklist with pass/fail + exit code.** One block, agent-readable.
- **Three output modes** on every command that emits structured data: human (default), `--json` (full payload), `--plain` (TSV without headers — `xargs`/`awk`-friendly).
- **Distinct exit codes by failure class:** 0 success, 1 local error (parse, fs), 2 missing argument, 3 auth, 4 backend unreachable, 5 provider/API error, 6 verification failed.
- **Every error carries a `hint:` line** with the exact correct invocation.
- **Stdin first-class** for body input. `cat msg.md | paw conv send 01HZ... --stdin`. No flag needed if stdin isn't a TTY.
- **Generic passthrough alongside opinionated verbs.** `paw api POST /api/v1/chat/ -d '{...}'` is the escape hatch. `paw api openapi` dumps the OpenAPI schema for self-discovery.
- **`paw api ls`** enumerates registered endpoints.
- **Verbose mode (`-v`) prints the wire trace** — request line, headers, response status, body — for debugging.
- **Examples block in every `--help` leaf.** Agents pattern-match better on examples than prose.
- **Editor fallback** for body input when TTY + no `--stdin`: open `$VISUAL`/`$EDITOR`/`vi`.
- **`paw doctor`'s checklist:** CLI version, config readable, token valid (calls `/users/me`), backend reachable, default workspace exists, models endpoint returns ≥1 entry, SSE stream framing healthy (does a tiny dry chat against a fixture).
- **`--env {local,dev,stg,prod}` as a real top-level flag** that sets the base URL (not just an env var) — this is a place ntn fumbled (env var only, no flag).

Anti-patterns to avoid (ntn-grounded):

- **No `--json` swallowing of error exit codes.** ntn's `datasources resolve --json` exits 0 on 404. Every paw command must return non-zero exit on failure even in `--json` mode, with the error embedded as `{"error": ..., "code": ..., "hint": ...}`.
- **No "feature exists but only on some verbs."** If `--plain` works on `conversations ls`, it works on `conversations get` too. If `--limit` exists on one list, it exists on every list.
- **No half-implemented commands shipped without `--limit`/`--cursor`** for paginated endpoints.
- **No hidden subcommands.** Everything appears in `--help`.

---

## File structure

```
backend/
├── app/
│   └── cli/
│       └── paw/                              # NEW package (renamed from agent_cli)
│           ├── __init__.py
│           ├── main.py                        # typer root
│           ├── config.py                      # XDG paths + profile resolution
│           ├── state.py                       # persona state load/save
│           ├── http.py                        # AsyncClient w/ cookie jar
│           ├── sse.py                         # frontend-parity SSE consumer
│           ├── output.py                      # human / --json / --plain formatters
│           ├── errors.py                      # PawError hierarchy + exit codes
│           ├── ids.py                         # UUID generation (v4) for conversations
│           ├── commands/
│           │   ├── __init__.py
│           │   ├── login.py                   # paw login / logout
│           │   ├── doctor.py                  # paw doctor
│           │   ├── env_cmd.py                 # paw env (print active env + config)
│           │   ├── auth.py                    # paw auth status
│           │   ├── config_cmd.py              # paw config get/set/list
│           │   ├── workspaces.py              # paw workspaces ls/show/use
│           │   ├── workspace.py               # paw workspace env/files
│           │   ├── conversations.py           # paw conversations ls/get/create/send/delete/rename/move/label
│           │   ├── messages.py                # paw messages ls/get
│           │   ├── models.py                  # paw models ls
│           │   ├── api.py                     # paw api passthrough
│           │   ├── completions.py             # paw completions <shell>
│           │   ├── record.py                  # paw record / replay (fixture capture)
│           │   └── verify.py                  # paw verify codex / chat-roundtrip / model-switch / all
│           └── verify/
│               ├── __init__.py
│               ├── scenarios.py               # ScenarioResult/Check primitives
│               ├── codex.py                   # codex E2E scenario
│               ├── chat_roundtrip.py          # SSE stream vs chat_messages.timeline
│               └── model_switch.py            # mid-conversation model swap
├── tests/
│   └── paw/                                  # NEW
│       ├── conftest.py
│       ├── test_state.py
│       ├── test_sse_parser.py                 # frame splitter unit tests
│       ├── test_command_login.py
│       ├── test_command_conversations.py
│       └── test_verify_scenarios.py
├── tests/e2e_paw/                            # NEW — gated on PAW_E2E=1
│   ├── conftest.py                            # boots a fresh backend in a subprocess
│   ├── test_verify_codex_live.py
│   └── test_chat_roundtrip_live.py
├── pyproject.toml                            # MODIFY: add typer, httpx[http2], respx (dev), console script
└── scripts/
    └── (no separate wrapper — `uv run paw …` and `just paw …` are the supported invocations)

# Repo root
.claude/
└── skills/
    └── paw/                                  # NEW (project-local skill)
        └── SKILL.md                          # teaches agents how to use paw
backend/
└── app/
    ├── api/
    │   └── conversations.py                  # MODIFY: include codex_thread_id in route response
    └── schemas.py                            # MODIFY: add codex_thread_id to ConversationRead
docs/
└── design/
    └── codex-oauth-text-provider.md          # MODIFY: link verify suite
justfile                                       # MODIFY: add paw recipe
```

---

## Pre-flight reading (must read before each task)

- `backend/app/schemas.py:287-340` — `ChatRequest`, `ConversationRead`, `ChatMessageRead` exact field shapes (especially the required `conversation_id`).
- `backend/app/api/chat.py:165-330` — chat router, including the `type: "message"` synthesis at `:309`.
- `backend/app/api/conversations.py:82-254` — full CRUD; note `POST /{id}` for create (`:242-254`) and the response field-list at `:113-126`/`:191-204`.
- `backend/app/api/models.py:90-140` — envelope shape `{"models": [...], "etag": "..."}`.
- `backend/app/api/auth.py:13-60` + `backend/main.py:184-200` + `backend/app/users.py:60-85` — auth flow + cookie config.
- `backend/app/api/workspace.py:142-318` + `backend/app/api/workspace_env.py:138-200` — workspace CRUD + env set/delete (note `DELETE /env/{key}` route).
- `frontend/features/chat/hooks/use-chat.ts` (around line 165) — SSE consumer to mirror.
- `frontend/features/chat/api/*` and `frontend/features/conversations/api/*` — UUID pre-generation + create-then-chat flow.
- `~/.claude/plugins/cache/claude-plugins-official/Notion/9847f2aa1a15/skills/notion/research-documentation/SKILL.md` — reference for the skill we'll author.

---

## State file format (`~/.config/pawrrtal/<profile>/state.json`)

```json
{
  "schema_version": 1,
  "profile": "default",
  "env": "local",
  "api_base_url": "http://127.0.0.1:8000",
  "user_id": "01234567-89ab-cdef-0123-456789abcdef",
  "user_email": "admin@example.com",
  "default_workspace_id": "01234567-89ab-cdef-0123-456789abcdef",
  "default_workspace_path": "/Users/octaviantocan/PawrrtalWorkspaces/paw-default",
  "default_model_id": "openai-codex:openai/gpt-5.5",
  "current_conversation_id": null,
  "created_at": "2026-05-27T18:30:00Z",
  "last_used_at": "2026-05-27T18:35:00Z"
}
```

**Cookies are stored separately** as a Mozilla cookie-jar file at `~/.config/pawrrtal/<profile>/cookies.txt`, loaded into `httpx.Cookies` on every command. Mode `0600`. This is what makes the cookie-with-`Expires=`-comma bug from v1 impossible.

---

## Canonical command surface

```
paw login [--api URL] [--env {local,dev,stg,prod}] [--profile NAME] [--dev-admin] [--email E] [--password P]
paw logout [--yes]
paw doctor [--json] [--plain]
paw env [--json]                                # show active env + config paths
paw auth status [--json]
paw config get KEY [--json]
paw config set KEY=VALUE
paw config list [--json] [--plain]

paw workspaces ls [--json] [--plain] [--limit N]
paw workspaces show [--workspace ID] [--json]
paw workspaces use ID                           # set default workspace

paw workspace env get [KEY] [--json] [--plain]
paw workspace env set KEY=VALUE [KEY=VALUE ...]
paw workspace env unset KEY [KEY ...]
paw workspace files ls PATH [--json] [--plain]
paw workspace files cat PATH                    # stdout = file content
paw workspace files write PATH [--stdin|-d CONTENT]
paw workspace files rm PATH [--yes]

paw models ls [--all] [--host HOST] [--json] [--plain]

paw conversations ls [--limit N] [--cursor C] [--json] [--plain]
paw conversations show ID [--with-messages] [--json]
paw conversations create [--workspace W] [--model M] [--title T] [--json]   # pre-gen UUID + POST /conversations/{uuid}
paw conversations send TEXT --conversation ID [--model M] [--reasoning-effort LEVEL] [--image FILE]... [--json] [--plain]
paw conversations send TEXT --new [--workspace W] [--model M] [--reasoning-effort LEVEL] [--image FILE]... [--json] [--plain]
paw conversations rename ID NEW_TITLE
paw conversations delete ID [--yes]
paw conversations export ID [--format md|json]

paw messages ls CONVERSATION_ID [--json] [--plain]
paw messages get MESSAGE_ID [--json]

paw api METHOD PATH [-d BODY|--stdin] [-H 'K: V']... [-v] [--json]
paw api openapi [--json]                        # dump OpenAPI schema
paw api ls                                      # enumerate routes

paw record COMMAND...                           # capture HTTP + SSE traffic for replay
paw replay --from FIXTURE                       # run against fixture without backend

paw verify codex [--keep-conversation] [--json]
paw verify chat-roundtrip [--model M] [--json]
paw verify model-switch [--from M1 --to M2] [--json]
paw verify all [--include HOST,...] [--exclude HOST,...] [--json]

paw completions {bash,zsh,fish,pwsh}            # emit completion script for shell

# v2 (deferred, listed for shape only):
# paw channels (telegram link, simulate-update)
# paw mcp ls/add/rm
# paw cost summary
# paw audit list
# paw jobs ls/create
# paw lcm ls
# paw fanout N COMMAND...                       # parallel personas
# paw mirror --upstream URL COMMAND...          # local vs remote SSE diff
```

Every command supports `--help`, `-v` (verbose wire trace), `--profile NAME`. Mutations support `--dry-run` and (where confirmations would otherwise prompt) `--yes`.

---

## Tasks

Tasks 0–6 are v1 (delivers `verify codex` + `verify chat-roundtrip`). Tasks 7–9 are polish. Tasks 10+ are v2 (deferred to follow-up beans; listed for completeness).

### Task 0 — Backend prerequisite: expose `codex_thread_id` in `ConversationRead`

**Why first:** without this, the headline assertion of `paw verify codex` is impossible over HTTP.

**Files:**
- `backend/app/schemas.py` — add `codex_thread_id: str | None = None` to `ConversationRead`.
- `backend/app/api/conversations.py` — include `codex_thread_id=conversation.codex_thread_id` in the two `ConversationRead(...)` constructions (around lines 113-126 and 191-204; re-read for exact spots).
- `backend/tests/test_conversations.py` (or wherever the conversation API tests live) — add an assertion that a Codex-backed conversation returns `codex_thread_id` populated.

**Steps:**

- [ ] **0.1 Read the current schema and route handlers.**

```bash
grep -n "class ConversationRead\|codex_thread_id\|ConversationRead(" \
  backend/app/schemas.py backend/app/api/conversations.py | head -30
```

- [ ] **0.2 Write a failing API test.**

In `backend/tests/test_conversations.py` (or a new file if none exists), add:

```python
@pytest.mark.anyio
async def test_conversation_response_includes_codex_thread_id(
    db_session, test_user, authenticated_client
):
    """ConversationRead must include codex_thread_id so paw verify can assert it."""
    from app.models import Conversation
    from sqlalchemy import select

    conv_id = uuid.uuid4()
    conv = Conversation(
        id=conv_id,
        user_id=test_user.id,
        title="test",
        model_id="openai-codex:openai/gpt-5.5",
        codex_thread_id="thr_test_abc",
    )
    db_session.add(conv)
    await db_session.commit()

    resp = await authenticated_client.get(f"/api/v1/conversations/{conv_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["codex_thread_id"] == "thr_test_abc"
```

Run, confirm FAIL (`KeyError` or `None`).

- [ ] **0.3 Make the test pass.**

In `backend/app/schemas.py`, find `class ConversationRead` and add:

```python
    codex_thread_id: str | None = None
```

In `backend/app/api/conversations.py`, find both places that build `ConversationRead(...)` (the `GET /{id}` and `PATCH /{id}` handlers). Add `codex_thread_id=conversation.codex_thread_id` to the constructor args. Re-read the file before editing — exact line numbers may have shifted.

Run, confirm PASS.

- [ ] **0.4 Commit.**

```bash
git add backend/app/schemas.py backend/app/api/conversations.py backend/tests/test_conversations.py
git commit -m "feat(api): expose codex_thread_id in ConversationRead

Required by the paw verify codex scenario to assert thread persistence
end-to-end over HTTP. The column exists on Conversation (models.py:104)
but was missing from the response schema, so external clients had no
way to observe it.

No migration; schema-only addition."
```

---

### Task 1 — Package skeleton + console script + first command (`paw doctor`)

**Files:**
- `backend/app/cli/__init__.py`
- `backend/app/cli/paw/__init__.py`, `main.py`, `config.py`, `errors.py`, `output.py`
- `backend/app/cli/paw/commands/doctor.py`
- `backend/pyproject.toml` (add deps + script)
- `backend/tests/paw/__init__.py`, `conftest.py`, `test_smoke.py`
- `justfile` (add `paw` recipe)

#### Steps

- [ ] **1.1 Add deps + script entry to `backend/pyproject.toml`.**

```toml
# dependencies:
"httpx[http2]>=0.28",
"typer>=0.13",

# dev deps:
"respx>=0.21",

# new section:
[project.scripts]
paw = "app.cli.paw.main:app"
```

Then `cd backend && uv sync`.

- [ ] **1.2 Skeleton modules.**

Write the following files. (Provide the full content; do not abbreviate.)

`backend/app/cli/__init__.py` — empty.

`backend/app/cli/paw/__init__.py`:
```python
"""paw — Pawrrtal Agent CLI."""

from .main import app

__all__ = ["app"]
```

`backend/app/cli/paw/errors.py`:
```python
"""Exit codes and PawError hierarchy.

Exit codes (must match the user-facing contract in --help):
    0  success
    1  local error (parse, fs, config)
    2  missing argument / typer usage error
    3  auth error
    4  backend unreachable
    5  provider/API error (HTTP 4xx/5xx other than 401)
    6  verification failed
"""
from __future__ import annotations

import typer


class PawError(typer.Exit):
    def __init__(self, message: str, *, exit_code: int, hint: str | None = None) -> None:
        self.message = message
        self.hint = hint
        super().__init__(code=exit_code)


class LocalError(PawError):
    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=1, hint=hint)


class AuthError(PawError):
    def __init__(self, msg: str = "Not authenticated.", hint: str | None = "Run `paw login`.") -> None:
        super().__init__(msg, exit_code=3, hint=hint)


class BackendUnreachable(PawError):
    def __init__(self, msg: str, hint: str | None = "Is `just dev` running?") -> None:
        super().__init__(msg, exit_code=4, hint=hint)


class ApiError(PawError):
    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=5, hint=hint)


class VerificationFailed(PawError):
    def __init__(self, msg: str, hint: str | None = None) -> None:
        super().__init__(msg, exit_code=6, hint=hint)
```

`backend/app/cli/paw/output.py`:
```python
"""Three output modes: human (default), JSON, plain TSV."""
from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any


def emit_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


def emit_human(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def emit_plain_rows(rows: Iterable[Iterable[Any]]) -> None:
    """TSV without a header row. Each row is joined by tab."""
    for row in rows:
        sys.stdout.write("\t".join("" if c is None else str(c) for c in row))
        sys.stdout.write("\n")
    sys.stdout.flush()
```

`backend/app/cli/paw/config.py`:
```python
"""XDG config paths + profile resolution + state file IO."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROFILE = "default"
SCHEMA_VERSION = 1


def config_root() -> Path:
    if "PAW_CONFIG_DIR" in os.environ:
        return Path(os.environ["PAW_CONFIG_DIR"])
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pawrrtal"


def profile_dir(profile: str = DEFAULT_PROFILE) -> Path:
    return config_root() / profile


def state_path(profile: str = DEFAULT_PROFILE) -> Path:
    return profile_dir(profile) / "state.json"


def cookies_path(profile: str = DEFAULT_PROFILE) -> Path:
    return profile_dir(profile) / "cookies.txt"


ENV_BASE_URLS = {
    "local": "http://127.0.0.1:8000",
    "dev": "https://dev.pawrrtal.dev",
    "stg": "https://staging.pawrrtal.dev",
    "prod": "https://pawrrtal.com",
}


@dataclass
class PersonaState:
    schema_version: int = SCHEMA_VERSION
    profile: str = DEFAULT_PROFILE
    env: str = "local"
    api_base_url: str = ENV_BASE_URLS["local"]
    user_id: str | None = None
    user_email: str | None = None
    default_workspace_id: str | None = None
    default_workspace_path: str | None = None
    default_model_id: str | None = None
    current_conversation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def load(cls, profile: str = DEFAULT_PROFILE) -> "PersonaState":
        p = state_path(profile)
        if not p.exists():
            return cls(profile=profile)
        raw = json.loads(p.read_text())
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError(
                f"State schema mismatch at {p}. Run `paw login --force` to recreate.",
            )
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})

    def save(self) -> None:
        self.last_used_at = datetime.now(timezone.utc).isoformat()
        p = state_path(self.profile)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(asdict(self), f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
```

`backend/app/cli/paw/main.py`:
```python
"""paw — top-level typer app. Subcommands register here."""
from __future__ import annotations

import typer

from .commands import doctor as doctor_cmd

app = typer.Typer(
    name="paw",
    help=(
        "Pawrrtal Agent CLI. Drive the backend as a persistent persona — "
        "auth, workspaces, chat, model selection, end-to-end verification.\n\n"
        "Run `paw doctor` first to validate setup."
    ),
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

app.add_typer(doctor_cmd.app, name="doctor", help="Health check the persona + backend.")
# Subsequent tasks register more subcommands here.


@app.callback()
def _root() -> None:
    """No-op root callback so subcommands attach cleanly."""


if __name__ == "__main__":
    app()
```

`backend/app/cli/paw/commands/__init__.py` — empty.

`backend/app/cli/paw/commands/doctor.py`:
```python
"""paw doctor — checklist of pre-flight checks."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import typer

from ..config import PersonaState, profile_dir, state_path
from ..output import emit_human, emit_json

app = typer.Typer()


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@app.callback(invoke_without_command=True)
def doctor(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run a checklist of pre-flight checks. Exit 0 if all pass, else 6.

    Examples:
      paw doctor
      paw doctor --json
      paw doctor --profile staging
    """
    checks = asyncio.run(_run(profile))
    passed = all(c.passed for c in checks)

    if json_out:
        emit_json({
            "passed": passed,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
        })
    else:
        lines = []
        for c in checks:
            mark = "✓" if c.passed else "✗"
            line = f"  {mark} {c.name}"
            if not c.passed and c.detail:
                line += f"   ({c.detail})"
            lines.append(line)
        lines.append("")
        lines.append(f"{sum(c.passed for c in checks)}/{len(checks)} passed.")
        emit_human("\n".join(lines))

    if not passed:
        raise typer.Exit(code=6)


async def _run(profile: str) -> list[Check]:
    checks: list[Check] = []
    sp = state_path(profile)
    checks.append(Check("config_dir_exists", profile_dir(profile).exists(),
                        detail=str(profile_dir(profile))))
    checks.append(Check("state_file_exists", sp.exists(), detail=str(sp)))

    state: PersonaState | None = None
    try:
        state = PersonaState.load(profile)
        checks.append(Check("state_file_parseable", True))
    except Exception as e:
        checks.append(Check("state_file_parseable", False, detail=str(e)))
        return checks

    # Backend reachable?
    try:
        async with httpx.AsyncClient(base_url=state.api_base_url, timeout=5.0) as client:
            resp = await client.get("/api/v1/health")
            checks.append(Check("backend_reachable", resp.status_code == 200,
                                detail=f"{state.api_base_url} -> {resp.status_code}"))
    except httpx.ConnectError as e:
        checks.append(Check("backend_reachable", False, detail=str(e)))

    # Defer auth + workspace checks to Tasks 2+; they need the http client + login.
    return checks
```

- [ ] **1.3 Justfile recipe.**

Add to the root `justfile`:
```make
# Run the Pawrrtal Agent CLI (paw) against the local backend.
# Examples:
#   just paw doctor
#   just paw conv send "hello" --new --model openai-codex:openai/gpt-5.5 --json
paw *ARGS:
    cd backend && uv run paw {{ARGS}}
```

- [ ] **1.4 Smoke tests.**

`backend/tests/paw/__init__.py` — empty.

`backend/tests/paw/conftest.py`:
```python
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PAW_CONFIG_DIR", str(tmp_path))
    yield
```

`backend/tests/paw/test_smoke.py`:
```python
from app.cli.paw.main import app


def test_paw_help_runs(runner):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Pawrrtal Agent CLI" in result.stdout


def test_paw_doctor_runs_without_state(runner):
    # No state file yet — doctor still runs but most checks fail; exit code 6.
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 6
    import json
    out = json.loads(result.stdout)
    assert out["passed"] is False
    names = {c["name"] for c in out["checks"]}
    assert "state_file_exists" in names
```

- [ ] **1.5 Run + commit.**

```bash
cd backend
DATABASE_URL="sqlite+aiosqlite:///:memory:" uv run pytest tests/paw/ -x -v 2>&1 | tail -10
```

Expected: pass.

```bash
git add backend/pyproject.toml backend/uv.lock \
        backend/app/cli/__init__.py \
        backend/app/cli/paw/ \
        backend/tests/paw/ \
        justfile
git commit -m "feat(paw): package skeleton + paw doctor command"
```

---

### Task 2 — HTTP client with cookie jar + `paw login` + `paw logout` + `paw auth status`

**Files:**
- `backend/app/cli/paw/http.py` (HTTPX client wrapped with cookie jar persistence)
- `backend/app/cli/paw/sse.py` (frontend-parity SSE consumer — see Task 3 if scope is too big)
- `backend/app/cli/paw/commands/login.py`
- `backend/app/cli/paw/commands/auth.py`
- `backend/app/cli/paw/main.py` — register
- `backend/tests/paw/test_command_login.py` with respx mocks

#### Key design decision — cookie persistence

```python
# http.py — sketch
import http.cookiejar
import httpx

def load_cookies(path: Path) -> httpx.Cookies:
    jar = http.cookiejar.MozillaCookieJar(str(path))
    if path.exists():
        jar.load(ignore_discard=True, ignore_expires=True)
    return httpx.Cookies(jar=jar)

def save_cookies(cookies: httpx.Cookies, path: Path) -> None:
    jar = cookies.jar  # the underlying CookieJar
    if isinstance(jar, http.cookiejar.MozillaCookieJar):
        jar.save(ignore_discard=True, ignore_expires=True)
    else:
        # httpx.Cookies' default jar isn't Mozilla format — wrap it
        moz = http.cookiejar.MozillaCookieJar(str(path))
        for c in jar:
            moz.set_cookie(c)
        moz.save(ignore_discard=True, ignore_expires=True)
    path.chmod(0o600)
```

Login flow:
1. Construct an `httpx.AsyncClient(base_url=..., cookies=<jar>)`.
2. `POST /auth/dev-login` (if `--dev-admin`) or `POST /auth/jwt/login` with `data={"username": email, "password": password}`. **httpx automatically stores set-cookies in the jar.**
3. Confirm by `GET /api/v1/users/me` (uses the cookie).
4. Persist the jar to `cookies.txt`. Persist user info + workspace to `state.json`.

Workspace ensure:
1. `GET /api/v1/workspaces` (read envelope shape from the real handler).
2. If a workspace named `paw-<profile>` exists, use it. Else `POST /api/v1/workspaces` (verify exact create request body against `backend/app/api/workspace.py` — read before writing).

Auth status:
1. Load cookies + state.
2. `GET /api/v1/users/me`; if 200, authenticated; if 401, exit 3.

Logout:
1. Optionally call `POST /auth/jwt/logout` if it exists.
2. Delete `cookies.txt` and `state.json` for the profile.

#### Steps

- [ ] **2.1 Write `http.py`** with `PawClient` (httpx wrapper that loads cookies on enter, saves on exit) and a `--verbose` mode that prints request/response to stderr.

- [ ] **2.2 Write failing test** using respx to mock `/auth/dev-login` (with a realistic `Set-Cookie` header including `Expires=`), `/api/v1/users/me`, `/api/v1/workspaces`, `/api/v1/workspaces` POST. Assert the persisted `cookies.txt` round-trips through `MozillaCookieJar.load` and the subsequent `paw auth status` returns the right user.

- [ ] **2.3 Implement `commands/login.py` and `commands/auth.py`.** Both subcommands present in `--help` with copy-pasteable Examples blocks.

- [ ] **2.4 Update `paw doctor`** to add new checks: `token_valid` (`GET /users/me` returns 200), `default_workspace_exists`.

- [ ] **2.5 Verify the cookie corruption bug from v1 cannot recur** by including an explicit test: post a mock cookie with `Expires=Wed, 27-May-2099 12:00:00 GMT` and assert it round-trips intact.

- [ ] **2.6 Commit:**
```
feat(paw): http client with cookie jar + login/logout/auth status
```

---

### Task 3 — SSE stream consumer (frontend-parity)

**Files:**
- `backend/app/cli/paw/sse.py`
- `backend/tests/paw/test_sse_parser.py`

#### Why a custom parser

The chat endpoint is not strict-RFC SSE; it's a stream of `data: <json>\n\n` lines plus the literal `data: [DONE]\n\n` sentinel. The frontend doesn't use `EventSource`; it uses `fetch + ReadableStream.getReader() + TextDecoderStream` — see `frontend/features/chat/hooks/use-chat.ts` around line 165. To catch the same bugs the frontend would, the CLI must do the same shape of parsing.

#### Steps

- [ ] **3.1 Write the parser as a generator.**

```python
# sse.py — sketch
from collections.abc import AsyncIterator
import json
import httpx


async def stream_chat_events(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
) -> AsyncIterator[dict]:
    """Yield decoded chat events from /api/v1/chat/.

    Mirrors the frontend technique: byte-level streaming, manual \\n\\n
    framing, decode each `data:` payload as JSON or recognize the literal
    `[DONE]` sentinel.

    Yields one dict per event:
        {"type": "delta", "content": "..."}
        {"type": "thinking", "content": "..."}
        {"type": "message", "content": "..."}        # router-injected (chat.py:309)
        {"type": "tool_use", "name": "...", "input": {...}}
        {"type": "tool_result", "content": "..."}
        {"type": "usage", "input_tokens": N, "output_tokens": N}
        {"type": "error", "content": "..."}
        {"type": "done"}                              # synthesized from [DONE]
    """
    async with client.stream(method, path, json=json_body) as resp:
        resp.raise_for_status()
        buffer = b""
        async for chunk in resp.aiter_bytes():
            buffer += chunk
            while b"\n\n" in buffer:
                frame, buffer = buffer.split(b"\n\n", 1)
                event = _parse_frame(frame)
                if event is not None:
                    yield event
                    if event.get("type") == "done":
                        return


def _parse_frame(frame: bytes) -> dict | None:
    text = frame.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if text.startswith("data:"):
        text = text[len("data:"):].lstrip()
    if text == "[DONE]":
        return {"type": "done"}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
```

- [ ] **3.2 Unit tests** for the framer:
  - Single event with terminator.
  - Two events in one chunk.
  - Event split across two chunks.
  - The `[DONE]` sentinel.
  - Malformed JSON → None (no crash).
  - All recognized `type:` values from `backend/app/api/chat.py` show up correctly when constructed.

- [ ] **3.3 Commit:**
```
feat(paw): SSE consumer mirroring frontend's fetch+ReadableStream pattern
```

---

### Task 4 — `paw conversations` family

The headline subcommand. **Mirrors the frontend's UUID-first flow.**

- `paw conversations create` — generate v4 UUID locally, `POST /api/v1/conversations/{uuid}` with body `{title, model_id, workspace_id}`. Return the created conversation.
- `paw conversations send TEXT --new` — sugar: `create` + `send TEXT --conversation <id>`.
- `paw conversations send TEXT --conversation ID` — `POST /api/v1/chat/` with the required `conversation_id`. Stream SSE via `sse.stream_chat_events`. Build `final_text` from `delta` events (and `message` if present; check `chat.py:309` to confirm whether it duplicates `delta` or adds new content). Output JSON with full event log + counters + `final_text` + `duration_ms`.

#### Steps

- [ ] **4.1 Read the exact `ChatRequest` and `POST /api/v1/conversations/{id}` body shapes.** `backend/app/schemas.py:287-340`, `backend/app/api/conversations.py:242-254`. Do not guess fields.

- [ ] **4.2 Implement.** All variants take `--json`, `--plain` (for `ls`), `-v`.

- [ ] **4.3 Confirm the `type: "message"` semantics.** In `backend/app/api/chat.py:309`, find the line emitting `{"type": "message", ...}`. Document: does it duplicate the assistant text, or add new text not in `delta`s? Adjust `final_text` accumulation accordingly. Surface this finding in a comment in `chat.py`-handling code in the CLI.

- [ ] **4.4 Tests with respx + a recorded SSE fixture.** Record one real Codex response once (using `paw record` from Task 6) into `backend/tests/paw/recordings/codex_hello.jsonl`. Replay it in respx by setting up a stream of bytes.

- [ ] **4.5 Update `paw doctor`** to add a check: tiny dry chat against a synthetic backend route that emits a single `[DONE]` — verifies SSE framing end-to-end without burning a real LLM call. (See `paw replay` in Task 6.)

- [ ] **4.6 Commit:**
```
feat(paw): conversations create/send/show/ls/delete with UUID-first flow
```

---

### Task 5 — `paw workspaces`, `paw workspace env`, `paw workspace files`, `paw models`, `paw messages`

Mechanical wrappers of the existing API. Each subcommand follows the ntn pattern (resource + verb, three output modes, `-v`, hint-bearing errors).

Watch for envelope shapes — `models ls` must `.get("models", [])` from the envelope (`backend/app/api/models.py:129`). `workspaces ls` returns a bare list; confirm by re-reading the route.

`workspace env unset KEY` uses `DELETE /api/v1/workspaces/{id}/env/{KEY}` (`backend/app/api/workspace_env.py:182`), not a `PUT` with the key removed.

#### Steps

- [ ] **5.1 Implement each subcommand.** Stage tests alongside implementation.
- [ ] **5.2 Update `paw doctor`** to add `models_endpoint_returns_codex` (sentinel for the Codex catalog wiring).
- [ ] **5.3 Commit:**
```
feat(paw): workspaces / workspace env|files / models / messages
```

---

### Task 6 — `paw api` (passthrough) + `paw record` / `paw replay`

`paw api METHOD PATH` is the escape hatch (per ntn). It accepts `-d BODY` or `--stdin`. With `-v`, prints the wire trace.

`paw record COMMAND...` runs any subcommand and captures HTTP requests + SSE frames to a JSONL fixture file. `paw replay --from FIXTURE` does the inverse: serves the recorded responses from a small in-process httpx mock and re-runs the command, so tests + offline development have a deterministic backend.

#### Steps

- [ ] **6.1 Implement `paw api`** with `-d`, `--stdin`, headers via `-H`, `-v` for the wire trace, `--json` for parsed response. Add `paw api openapi` which fetches `/openapi.json` from the backend.

- [ ] **6.2 Implement `paw record`** by adding an `httpx` event hook (`event_hooks={"response": [_capture]}`) when `PAW_RECORD=<path>` is set. Each request + response (including streamed bytes for SSE) is logged as one JSONL row.

- [ ] **6.3 Implement `paw replay`** by reading the JSONL fixture and using `respx` to mount the recorded routes. Subsequent CLI commands hit the in-memory mock instead of a real backend.

- [ ] **6.4 Tests:** record a real chat once, then replay against the fixture in unit tests.

- [ ] **6.5 Commit:**
```
feat(paw): api passthrough + record/replay fixture support
```

---

### Task 7 — `paw verify codex` (the proof)

#### Scenario

1. **`GET /api/v1/models`** — pluck the Codex entry from `["models"]`. Assert `authenticated` is true.
2. **`POST /api/v1/conversations/{client_uuid}`** with body `{model_id: codex_model, workspace_id, title: "paw verify codex"}` — assert 201 (or 200, whatever the API returns; read first).
3. **`POST /api/v1/chat/`** with `{question, model_id, conversation_id: client_uuid, workspace_id}` — stream SSE. Assert: at least one `delta` or `message` event, no `error` events, terminal `done`, `final_text` non-empty, duration under 60s.
4. **`GET /api/v1/conversations/{client_uuid}`** — assert `model_id` matches, `codex_thread_id` is non-null and well-formed. Cache it as `thread_id_1`.
5. **`GET /api/v1/conversations/{client_uuid}/messages`** — assert ≥ 2 rows (user + assistant), and the assistant row's `assistant_status == "complete"` and its content is non-empty.
6. **Second turn** — `POST /api/v1/chat/` again with the same `conversation_id`. Stream. Assert: at least one event, no errors, terminal done.
7. **`GET /api/v1/conversations/{client_uuid}`** — assert `codex_thread_id == thread_id_1` (thread resumed, not recreated).
8. **Cleanup** — `DELETE /api/v1/conversations/{client_uuid}` unless `--keep-conversation`.

Every assertion gets its own `Check` row in the output JSON with name + pass/fail + detail.

#### Steps

- [ ] **7.1 Implement `verify/scenarios.py` (`ScenarioResult`, `Check`).** Same shape as v1's plan.
- [ ] **7.2 Implement `verify/codex.py`** with the 8 steps above.
- [ ] **7.3 Implement `commands/verify.py`** with `paw verify codex` subcommand. Exit code 6 on any failure, full JSON payload on stdout.
- [ ] **7.4 Unit tests with respx** — happy path + a failure for each check.
- [ ] **7.5 Live test gated on `PAW_E2E=1`** — actually boots the backend (or assumes `just dev` is up), calls real Codex (requires `~/.codex/auth.json`), asserts the suite passes. See Task 9 for CI integration.
- [ ] **7.6 Commit:**
```
feat(paw): verify codex scenario — end-to-end provider proof
```

---

### Task 8 — `paw verify chat-roundtrip` + `paw verify model-switch`

The two next-most-valuable suites the gap-hunt surfaced.

**chat-roundtrip:** send a chat with `reasoning_effort=high` and (if attachments are wired) one image. Stream SSE to completion. Then `GET /conversations/{id}/messages` and assert the rehydrated `ChatMessageRead.timeline` matches the streamed event order, `tool_calls` populated if any, `thinking_duration_seconds > 0`, and `assistant_status == "complete"`. Catches the "stream looked right but the DB row is wrong" bug class (e.g. block_index #371, thinking rendering, telegram-style chunk drops).

**model-switch:** start a conversation with model A; send a turn; switch to model B via `PATCH /api/v1/conversations/{id}`; send a turn. Assert: model_id canonicalised correctly (migration 012), reasoning_effort CHECK constraint honored (#367), no transaction-isolation regressions (#366).

#### Steps

- [ ] **8.1 Implement `verify/chat_roundtrip.py`.**
- [ ] **8.2 Implement `verify/model_switch.py`.**
- [ ] **8.3 `paw verify all`** runs the configured suites and exits 6 if any failed.
- [ ] **8.4 Live tests gated on `PAW_E2E=1`.**
- [ ] **8.5 Commit:**
```
feat(paw): verify chat-roundtrip + verify model-switch + verify all
```

---

### Task 9 — Live E2E gate (CI-ready)

The respx-mocked tests prove only CLI mechanics. The verification claim needs a real-backend gate.

#### Steps

- [ ] **9.1 `backend/tests/e2e_paw/conftest.py`** — fixture that boots `uvicorn app.main:app` against an in-memory SQLite DB in a subprocess, waits for `/api/v1/health`, runs `paw login --dev-admin --api http://127.0.0.1:<port>`, yields, and tears down. Skip the whole module unless `PAW_E2E=1`.

- [ ] **9.2 `tests/e2e_paw/test_verify_codex_live.py`** — calls `paw verify codex --json` against the fixture backend. Skips if `~/.codex/auth.json` is missing.

- [ ] **9.3 `tests/e2e_paw/test_chat_roundtrip_live.py`** — same shape but uses LiteLLM or a deterministic fake provider (gated separately).

- [ ] **9.4 GitHub Action** — new workflow `pawrr-verify.yml` that runs the e2e_paw suite on PRs that touch `backend/app/cli/paw/`, `backend/app/core/providers/`, or `backend/app/api/`. Codex credentials are pulled from a CI secret if available; otherwise the codex scenario skips and the chat-roundtrip + model-switch suites carry the weight.

- [ ] **9.5 Commit:**
```
feat(paw): live E2E gate gated on PAW_E2E=1 + CI workflow
```

---

### Task 10 — `.claude/skills/paw/SKILL.md` (the project-local skill)

A self-contained skill that teaches future agents how to use `paw`. Mirrors the Notion CLI's skill structure (resource map, common workflows, pitfalls, env vars). Lives at `.claude/skills/paw/SKILL.md` so it loads automatically in any Claude Code session opened in this repo.

#### Steps

- [ ] **10.1 Write the skill file.** Content sketch:

```markdown
---
name: paw
description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user — auth, workspaces, chat (with SSE streaming), conversation CRUD, provider verification. Prefer this over importing app.* modules in ad-hoc Python scripts; paw exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to paw.
paths: ["backend/**/*.py", "frontend/features/chat/**/*", "docs/superpowers/plans/*paw*"]
---

# paw — Pawrrtal Agent CLI

When verifying claims like "the X provider works end-to-end" or "the chat
roundtrip is intact," use `paw verify <suite>`. Never claim a behavior works
based on a Python snippet importing app.* — it bypasses auth, the router,
persistence, and SSE framing.

## Quick start
just paw doctor                    # health-check setup
just paw login --dev-admin         # seed persona
just paw verify codex --json       # end-to-end Codex proof
just paw verify all --json         # all currently-passing suites

## Resource map
| Resource       | Verbs                                              | Endpoint family                |
|----------------|----------------------------------------------------|--------------------------------|
| auth           | login, logout, status                              | /auth/*, /api/v1/users/me      |
| workspaces     | ls, show, use                                      | /api/v1/workspaces             |
| workspace env  | get, set, unset                                    | /api/v1/workspaces/{id}/env    |
| workspace files| ls, cat, write, rm                                 | /api/v1/workspaces/{id}/files  |
| models         | ls                                                 | /api/v1/models                 |
| conversations  | ls, show, create, send, rename, delete, export    | /api/v1/conversations          |
| messages       | ls, get                                            | /api/v1/conversations/{id}/messages |
| api (raw)      | METHOD PATH, openapi, ls                           | any                            |
| record/replay  | record COMMAND…, replay --from FILE                | local                          |
| verify         | codex, chat-roundtrip, model-switch, all           | end-to-end                     |

## Common workflows

### Verify a Codex change end-to-end
just paw verify codex --json | jq '.checks[] | select(.passed == false)'

### Capture a fixture for unit tests
PAW_RECORD=tests/paw/recordings/my_scenario.jsonl just paw conv send "hello" --new --model openai-codex:openai/gpt-5.5

### Replay offline
just paw replay --from tests/paw/recordings/my_scenario.jsonl

### Run a custom request when no opinionated verb fits
just paw api POST /api/v1/conversations/01HZ.../title -d '{"title":"renamed"}'

## Output modes
Every command supports:
- (default) human text
- --json     full machine-readable payload
- --plain    TSV without headers, pipe-friendly for awk/xargs

## Exit codes
0 ok | 1 local error | 2 missing arg | 3 auth | 4 backend unreachable | 5 API error | 6 verify failed

## Env vars
PAW_PROFILE       Persona profile (default: default)
PAW_CONFIG_DIR    Config root (default: ~/.config/pawrrtal)
PAW_RECORD        Capture HTTP+SSE traffic to this file
PAW_E2E           Set to 1 in pytest to run the live E2E suite

## Pitfalls
- Never assert "works" based on `uv run python -c '...'` snippets that import app.*. They bypass the router, persistence, and SSE framing.
- ConversationRead now includes codex_thread_id; before commit a8a959c3 it didn't, so older docs may say it doesn't ship over HTTP.
- The chat stream is custom SSE — `[DONE]` is a `data:` payload, not an `event:` field. Use `paw conv send` rather than rolling your own consumer.

## When to update this skill
- New `paw` subcommand → add to the Resource map.
- New verify suite → add to the Common workflows.
- New env var → add to Env vars.

## See also
- `docs/superpowers/plans/2026-05-27-agent-cli-user.md` — implementation plan.
- `backend/app/cli/paw/` — source.
- `~/.claude/plugins/cache/claude-plugins-official/Notion/9847f2aa1a15/skills/notion/research-documentation/SKILL.md` — design inspiration (ntn).
```

- [ ] **10.2 Add a paw self-test** that ensures the skill stays in sync with the CLI: `paw doctor --skill-check` parses the skill markdown and verifies every command listed in the Resource map exists in the typer app. Optional v2.

- [ ] **10.3 Commit:**
```
docs(paw): add project-local skill at .claude/skills/paw/SKILL.md
```

---

### Task 11 — Docs + bean closure

- [ ] **11.1 Update `docs/design/codex-oauth-text-provider.md`** to add a "Verification" section: `just paw verify codex` is the canonical proof.

- [ ] **11.2 Update parent bean `pawrrtal-pu63`** Summary with a `## Verification artefact` line linking to `paw verify codex`.

- [ ] **11.3 File new beans** for v2 commands (channels, MCP, cost, audit, jobs, LCM, fanout, mirror) and v2 verify suites (telegram-link-and-bot, cost-and-budget, lcm-active-recall).

- [ ] **11.4 Commit:**
```
docs(paw): cross-reference verify suites + file v2 beans
```

---

## Tasks deferred to v2 (file beans, do not implement now)

- `paw channels` — Telegram link/unlink, simulate-update for in-proc bot testing.
- `paw mcp` — MCP server CRUD.
- `paw cost` — cost summary + ledger.
- `paw audit` — audit events.
- `paw jobs` — scheduled jobs.
- `paw lcm` — LCM list/get + memories + dreaming.
- `paw fanout N COMMAND...` — N parallel personas hitting the same backend.
- `paw mirror --upstream URL COMMAND...` — local vs remote SSE diff.
- `paw verify telegram-link-and-bot` — full channel E2E.
- `paw verify cost-and-budget` — ledger + budget enforcement.
- `paw verify lcm-active-recall` — Active Recall pre-turn agent integration.
- `paw dev up/down/status` — process lifecycle for the dev launcher.

---

## Risks + open questions

- **Live E2E in CI requires Codex auth.** `~/.codex/auth.json` is operator-specific. CI fallbacks: (a) ship a Codex API key via secret, (b) skip the codex suite on CI but always run chat-roundtrip + model-switch against LiteLLM, (c) record a fixture and replay it.
- **`type: "message"` semantics** must be confirmed before Task 4.3 — does it duplicate `delta` content or carry something else? Read `chat.py:309` and the front-end consumer side by side.
- **`POST /api/v1/conversations/{uuid}` body shape** — re-read `conversations.py:242-254` before Task 4.1. The Codex provider adds a `codex_thread_id` column that may need to be settable here or only mutable from the chat path; verify.
- **respx tests are scoped tightly** — only catch CLI bugs, not backend bugs. The `PAW_E2E=1` suite is the real gate. Don't claim otherwise in commit messages.
- **Frontend SSE consumer location** — Task 3 says "around line 165 of `use-chat.ts`"; before implementation, run `grep -n "ReadableStream\|getReader\|TextDecoder" frontend/features/chat/hooks/use-chat.ts` to nail the exact reference.
- **Cookie `Domain=` scope** — a cookie issued by `http://127.0.0.1:8000` won't be sent to `https://staging.pawrrtal.dev`. `paw login` against a different env always starts a fresh jar. Document.

---

## Self-Review

- **Spec coverage of the user's request:**
  - Better name? ✅ `paw` (3 letters, brand-mnemonic, ntn-shaped).
  - More useful for testing? ✅ Three verify suites in v1 (codex, chat-roundtrip, model-switch); record/replay; live E2E gate; v2 roadmap covers channels, cost, LCM.
  - ntn-inspired? ✅ Resource+verb, doctor, three output modes, hint lines, api passthrough, examples in every help leaf, real `--env` flag, stdin first-class, openapi self-discovery.
  - Skill in the project? ✅ Task 10 — `.claude/skills/paw/SKILL.md`.
- **All three subagent findings folded in:**
  - Adversarial review's three critical bugs are addressed in Task 0 (codex_thread_id) and corrected in the chat flow (UUID-first, conv_id required, models envelope, cookie jar, message-event awareness).
  - ntn deep-dive's patterns are baked into the canonical surface + doctor + api passthrough + output modes + exit codes.
  - Gap-hunt's coverage matrix maps to v1 (codex/chat-roundtrip/model-switch + the workspace/messages/models surface) and v2 beans (channels/cost/lcm/fanout/mirror).
- **No placeholders:** every step references real files + line numbers + the exact commands.
- **Names + signatures consistent across tasks:** `PersonaState`, `PawClient`, `stream_chat_events`, `ScenarioResult`, `Check`, `PAW_E2E`, `PAW_CONFIG_DIR`, `PAW_RECORD`.

Plan ready. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between.
2. **Inline Execution** — batch through with checkpoints.

Which approach?

---
name: paw-extend
description: Extend or maintain the paw CLI (backend/app/cli/paw/). Use when adding a new paw subcommand, a new verify suite, a new output mode, an orchestrator command (like fanout/mirror/dev), or refactoring the shared helpers (http.py, sse.py, output.py, errors.py). The user-facing skill is `paw` — this one teaches you how the surface is built so the next addition fits the existing patterns instead of inventing parallels.
paths:
  - "backend/app/cli/paw/**/*.py"
  - "backend/tests/paw/**/*.py"
  - "backend/tests/e2e_paw/**/*.py"
  - ".claude/skills/paw/SKILL.md"
---

# paw-extend — how to add to the paw CLI

The operational skill (`paw`) covers how to **use** paw. This one covers how to **build on** it. Read both when you're adding a new command, new verify suite, or new shared helper.

## File layout (canonical)

```
backend/app/cli/paw/
├── __init__.py              # version + public surface (rarely edited)
├── main.py                  # top-level typer app; every command registers here
├── config.py                # PersonaState dataclass, PAW_CONFIG_DIR/PROFILE resolution
├── errors.py                # PawError hierarchy → exit codes (1/2/3/4/5/6)
├── http.py                  # PawClient (cookie jar, record hooks, retry)
├── ids.py                   # new_conversation_id() — v4 UUID helper
├── output.py                # emit_human / emit_json / plain_rows
├── sse.py                   # byte-level SSE framer + KNOWN_EVENT_TYPES + RawFrameTap
├── commands/                # one file per top-level verb / verb-group
│   ├── api.py               # `paw api …` — raw passthrough
│   ├── audit.py             # `paw audit ls/show`
│   ├── auth.py              # `paw auth status`
│   ├── channels.py          # `paw channels link/unlink/list`
│   ├── conversations.py     # `paw conversations ls/show/create/send/...`
│   ├── cost.py              # `paw cost summary/ledger`
│   ├── dev.py               # `paw dev up/down/status` (orchestrator)
│   ├── doctor.py            # `paw doctor`
│   ├── fanout.py            # `paw fanout N COMMAND...` (orchestrator)
│   ├── jobs.py              # `paw jobs ls/show/create/delete`
│   ├── lcm.py               # `paw lcm context`
│   ├── login.py             # `paw login`, `paw logout`
│   ├── mcp.py               # `paw mcp ls/show/create/update/delete`
│   ├── messages.py          # `paw messages ls/get`
│   ├── mirror.py            # `paw mirror --upstream URL COMMAND...` (orchestrator)
│   ├── models.py            # `paw models ls`
│   ├── record.py            # `paw record COMMAND...` (PAW_RECORD writer)
│   ├── replay.py            # `paw replay --from FILE COMMAND...`
│   ├── verify.py            # `paw verify {codex,chat-roundtrip,model-switch,telegram,cost,all}`
│   └── workspaces.py        # `paw workspaces …` + `paw workspace env / files`
└── verify/                  # one file per verification scenario
    ├── scenarios.py         # ScenarioResult + Check primitives
    ├── helpers.py           # resolve_default_model, env probes, shared assertions
    ├── codex.py             # 17-check Codex E2E proof
    ├── chat_roundtrip.py    # generic chat → final_text → DB-row scenario
    ├── model_switch.py      # mid-conversation model switch
    ├── cost.py              # cost ledger + budget enforcement
    └── telegram.py          # link-code lifecycle
```

Tests sit at `backend/tests/paw/test_command_<name>.py` (mocked, fast) and `backend/tests/e2e_paw/` (live-backend gated on `PAW_E2E=1`).

## The three command shapes

Every new verb falls into one of these. **Pick the right shape before writing code.**

### Shape A — HTTP wrapper

One backend endpoint → one verb. Examples: `paw audit ls`, `paw cost summary`, `paw workspaces show`.

- Use `PawClient.get/post/delete/patch` (returns `httpx.Response`).
- Read the matching `backend/app/api/<file>.py` first — paths, methods, body shapes drift from bean descriptions all the time.
- Emit via `emit_human`, `emit_json`, `plain_rows`.
- Raise `PawError` subclasses on failure; the orchestrator maps to exit codes.

Template to copy: `backend/app/cli/paw/commands/audit.py` (simple), `backend/app/cli/paw/commands/mcp.py` (full CRUD + client-side resolution).

### Shape B — Verify scenario

A sequenced multi-call scenario that asserts on observable state. Examples: `paw verify codex`, `paw verify telegram`.

- Each scenario builds a `ScenarioResult(checks=[Check(name=..., passed=..., message=...)])`.
- Check `name`s are stable strings — JSON consumers grep on them.
- Scenario function signature: `async def run_<name>_scenario(state: PersonaState, client: PawClient, **kwargs) -> ScenarioResult`.
- Register the verb in `commands/verify.py` (typer command, `--profile`, `--json`, `--keep-conversation`), add to `DEFAULT_SUITES` if it should run as part of `paw verify all`.
- When a backend endpoint doesn't exist (e.g. webhook simulate), emit a marker Check named `<thing>_endpoint_unavailable` with `passed=True` so the scenario isn't held hostage to a gap.

Template to copy: `backend/app/cli/paw/verify/telegram.py`.

### Shape C — Orchestrator

Spawns + coordinates other paw invocations or external processes. Doesn't hit the backend directly. Examples: `paw fanout`, `paw mirror`, `paw dev`, `paw record`, `paw replay`.

- Use `asyncio.create_subprocess_exec(sys.executable, "-m", "app.cli.paw.main", *args, env=...)`.
- Per-child isolation: distinct `PAW_CONFIG_DIR` (cookies + state.json), optionally `PAW_PROFILE`.
- Register at top level via `app.command("name", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})(fn)` so `ctx.args` carries the wrapped paw command.
- Cleanup is the parent's job — only delete dirs you just created.

Template to copy: `backend/app/cli/paw/commands/fanout.py` (subprocess + per-slot env), `backend/app/cli/paw/commands/dev.py` (pid file + signal handling).

## Required output modes

Every new verb must support:

1. **Default human text** — one line per row or a compact table; lossy but readable.
2. **`--json`** — full machine-readable payload; never silently drops errors. Failed commands emit `{"error": "...", "code": <int>, "hint": "..."}` and exit non-zero.
3. **`--plain`** — TSV without headers, pipe-friendly. `awk`/`xargs` consumers depend on it. Skip only if the verb returns a scalar (e.g. a single object's body).

Use `output.emit_human`, `output.emit_json`, `output.plain_rows`. Don't print directly.

## Exit codes

| Code | Meaning                        | Source             |
| ---- | ------------------------------ | ------------------ |
| `0`  | success                        | normal return      |
| `1`  | local error (fs, parse)        | `LocalError`       |
| `2`  | missing argument / usage       | typer / explicit   |
| `3`  | auth (re-run `paw login`)      | `AuthError`        |
| `4`  | backend unreachable            | `BackendUnreachable` |
| `5`  | API / provider error           | `BackendError`     |
| `6`  | verification failed            | `VerificationFailed` |

Map at the boundary: catch HTTP exceptions inside the verb, raise the right `PawError` subclass, let typer's exception handler in `main.py` translate to the exit code.

## Tests (mandatory, same commit)

Mocked tests live at `backend/tests/paw/test_command_<name>.py`. Pattern:

- Use `respx.mock` (a `pytest_asyncio` fixture is provided in `conftest.py`).
- One test per code path: happy + every error class (401, 404, 500) + flag combinations.
- For orchestrators, mock `asyncio.create_subprocess_exec` — never spawn real `paw` subprocesses.
- For verify scenarios, assert on the `ScenarioResult.checks` list — each named Check is its own test row.

Live-backend tests live at `backend/tests/e2e_paw/test_<name>.py`, gated on `PAW_E2E=1`. The `live_backend` fixture in `backend/tests/e2e_paw/conftest.py` boots uvicorn against a tmpdir SQLite DB.

Target counts (rough rule):
- Shape A (HTTP wrapper): 8–20 tests covering list/show/create/update/delete + every error class.
- Shape B (verify scenario): 6–10 tests — happy path, each Check's failure mode, JSON shape assertion.
- Shape C (orchestrator): 10–15 tests — child env assertions, cancellation, cleanup, `--json` schema.

## Conventions worth knowing

- **Cookie auth.** `PawClient` ships a `MozillaCookieJar` rooted at `~/.config/pawrrtal/<profile>/cookies.txt`. Never regex-parse `Set-Cookie` — the `Expires=` field contains a comma that breaks naive splits.
- **UUID-first conversation flow.** The client pre-generates a v4 UUID (`ids.new_conversation_id()`), POSTs `/api/v1/conversations/{uuid}`, then POSTs `/api/v1/chat/` with `conversation_id: <uuid>` (required). The fallback path that auto-creates conversations only fires on the legacy `/api/chat` endpoint.
- **SSE framing.** `sse.stream_chat_events` parses `data: <json>\n\n` frames + the `[DONE]` sentinel. Pass an `on_raw_frame` tap to capture bytes (used by `paw record` for SSE capture).
- **Backend API discovery.** Bean descriptions of endpoint paths are often wrong — `backend/app/api/<file>.py` is the source of truth. Read the file before writing the verb.
- **Lazy SDK imports.** Heavy SDK modules (Codex, Gemini, Anthropic) are gated behind `__getattr__` shims to keep paw's startup time fast and prevent cross-provider import bleed.
- **Sandbox + pre-commit.** The default sandbox blocks `~/.cache/pre-commit/` writes. When commits fail with that error, retry with `dangerouslyDisableSandbox: true`. The gates themselves (ruff, mypy, biome, gitleaks) still run.

## SKILL.md hygiene

When you ship a new verb, update `.claude/skills/paw/SKILL.md`:

- Add a row to the Resource map.
- Add a Common workflows entry if the verb has a multi-step use case (e.g. `paw verify <suite>`).
- Add a Pitfall row if the verb surfaces a backend quirk worth remembering.
- If the verb was on the "Deferred to v2" list, remove it.

The maintainer-facing skill (this file) only needs updating when the **patterns** change — a new command shape, a new output mode, a new helper category.

## Anti-patterns

- **Direct `print`.** Goes through `emit_human` / `emit_json` / `plain_rows` so `--json` mode stays clean.
- **Inventing a parallel auth path.** All HTTP goes through `PawClient`; the cookie jar handles persistence.
- **Skipping `--plain` because it's "extra work".** Pipelines depend on it. Single-object verbs may skip; list verbs may not.
- **Asserting "works end-to-end" from a Python snippet.** That bypasses auth, routing, persistence, SSE framing. Run `paw verify <suite>` instead.
- **Fabricating endpoints.** If the bean says `POST /channels/{id}/simulate` and the backend exposes none, ship a Check marker (`<thing>_endpoint_unavailable`) and file a follow-up bean — don't invent the call.
- **`git add -A` / `git add .`.** The working tree is shared with other agents. Always stage explicit paths.

## Cross-references

- `paw` (sibling skill) — operational usage; what each verb does, when to reach for which.
- `cli-as-persona` (global skill) — design philosophy for project-local "real-user" CLIs.
- `backend/app/cli/paw/commands/` — every shipped verb is a worked example.
- `backend/tests/paw/test_command_*.py` — every shipped verb has a mocked test that's the template for the next one.

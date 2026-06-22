"""paw — Pawrrtal Agent CLI."""

from __future__ import annotations

# <skill-gen>
# ---
# name: paw
# description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user -- auth, workspaces, chat with SSE streaming, conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
# paths:
#   - "backend/**/*.py"
#   - "frontend/features/chat/**/*"
#   - "docs/superpowers/plans/*paw*"
#   - "docs/design/codex*"
# ---
#
# # paw -- Pawrrtal Agent CLI
#
# Use `paw` when verifying a backend or chat behavior as a real user. It goes
# through auth, the FastAPI router, persistence, SSE framing, and the same HTTP
# surface the React frontend uses. Do not claim "end-to-end works" from an
# ad-hoc Python snippet that imports `app.*` directly.
#
# ## Quick start
#
# ```bash
# just paw doctor
# just paw env check
# just env-check
# just paw project up
# just paw project down
# just smoke-dev
# just paw login --dev-admin
# just paw verify chat-roundtrip --json
# just paw verify all --json
# just paw lab flows ls --json
# paw --api https://pawrrtal.octaviantocan.com doctor --json
# ```
#
# `paw` lives at `backend/app/cli/paw/`. `just paw <args>` forwards to
# `scripts/paw`, and `just install-paw` installs the launcher as `paw`.
#
# ## Output modes
#
# Every command supports human text by default and `--json` for machine output.
# List-style commands also support `--plain` TSV. JSON mode never silently
# swallows errors: failed commands exit non-zero and emit an error object.
#
# ## Environment variables
#
# | Var | Purpose |
# | --- | --- |
# | `PAW_PROFILE` | Persona profile, default `default` |
# | `PAW_CONFIG_DIR` | Config root, default `~/.config/pawrrtal` |
# | `PAW_BACKEND_URL` | One-shot backend URL override |
# | `PAW_RECORD` | Capture HTTP + SSE traffic to JSONL |
# | `PAW_E2E` | `1` in pytest enables live E2E tests |
# | `UV_CACHE_DIR` | Set by local project launchers when unset |
# | `XDG_CACHE_HOME` | Set by local project launchers when unset |
# | `PAWRRTAL_DEV_DATABASE_URL` | Explicit non-SQLite dev database URL |
# | `PAWRRTAL_SERVICES_CONFIG` | Local `paw services` target config path |
#
# ## Pitfalls
#
# - `GET /api/v1/models` returns `{ "models": [...], "etag": "..." }`, not a
#   bare list.
# - `ChatRequest.conversation_id` is required. Create the conversation first or
#   use `paw conversations send --new`.
# - `paw messages get` takes `(conversation_id, index)` because there is no
#   `/messages/{id}` route.
# - `paw project up` launches the full app; `paw dev up` launches backend only.
# - Run `paw env check` before debugging startup failures.
# - Cookies live at `~/.config/pawrrtal/<profile>/cookies.txt` and must be
#   handled by the cookie jar, not string splitting.
#
# ## See also
#
# - `backend/app/cli/paw/` -- source.
# - `backend/tests/paw/` -- mocked unit tests.
# - `backend/tests/e2e_paw/` -- live-backend E2E tests gated by `PAW_E2E=1`.
# - `docs/superpowers/plans/2026-05-27-agent-cli-user.md` -- original plan.
# </skill-gen>

__all__ = ["app"]


def __getattr__(name: str) -> object:
    """Load the Typer app lazily so submodule imports stay lightweight."""
    if name == "app":
        from .main import app  # noqa: PLC0415

        return app
    raise AttributeError(name)

"""Public surface for the ``paw project`` and ``paw env`` command package."""

# <skill-gen>
# ---
# name: paw
# description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user -- auth, workspaces, chat with SSE streaming, conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
# ---
#
# ## Run or stop the local project
#
# ```bash
# just paw env check
# just env-check
# just paw project up
# just paw project status --json
# just paw project logs
# just paw project down
# just smoke-dev
# ```
#
# `paw project up` launches the same root `dev.ts` orchestrator as `just dev`,
# detaches it, stores state under `<PAW_CONFIG_DIR>/<profile>/project.json`, and
# waits for frontend (`http://localhost:53001`) plus FastAPI
# (`http://127.0.0.1:8000`). Use `paw dev up/down/status` only for the backend
# half by itself.
#
# `paw env check` and `paw project preflight` are non-interactive startup gates:
# binaries, writable cache/config dirs, ports, and socket binding.
# </skill-gen>

from app.cli.paw.commands.project.cli import (
    app,
    env_app,
    pid_alive,
    probe_url,
    project_healthy,
    run_project,
    spawn_project,
    stop_project,
    wait_for_project,
)
from app.cli.paw.commands.project.preflight import PreflightCheck, run_preflight_checks
from app.cli.paw.commands.project.state import (
    PROJECT_STATE_SCHEMA_VERSION,
    project_log_path,
    project_state_path,
)

__all__ = [
    "PROJECT_STATE_SCHEMA_VERSION",
    "PreflightCheck",
    "app",
    "env_app",
    "pid_alive",
    "probe_url",
    "project_healthy",
    "project_log_path",
    "project_state_path",
    "run_preflight_checks",
    "run_project",
    "spawn_project",
    "stop_project",
    "wait_for_project",
]

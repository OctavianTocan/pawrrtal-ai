"""paw — top-level typer app. Subcommands register here."""

from __future__ import annotations

import os

import typer

from app.cli.paw.commands import admin as admin_cmd
from app.cli.paw.commands import api as api_cmd
from app.cli.paw.commands import appearance as appearance_cmd
from app.cli.paw.commands import audit as audit_cmd
from app.cli.paw.commands import auth as auth_cmd
from app.cli.paw.commands import channels as channels_cmd
from app.cli.paw.commands import completions as completions_cmd
from app.cli.paw.commands import conversations as conversations_cmd
from app.cli.paw.commands import cost as cost_cmd
from app.cli.paw.commands import dev as dev_cmd
from app.cli.paw.commands import doctor as doctor_cmd
from app.cli.paw.commands import fanout as fanout_cmd
from app.cli.paw.commands import heartbeat as heartbeat_cmd
from app.cli.paw.commands import jobs as jobs_cmd
from app.cli.paw.commands import lab as lab_cmd
from app.cli.paw.commands import lcm as lcm_cmd
from app.cli.paw.commands import login as login_cmd
from app.cli.paw.commands import mcp as mcp_cmd
from app.cli.paw.commands import messages as messages_cmd
from app.cli.paw.commands import mirror as mirror_cmd
from app.cli.paw.commands import models as models_cmd
from app.cli.paw.commands import personalization as personalization_cmd
from app.cli.paw.commands import plugins as plugins_cmd
from app.cli.paw.commands import project as project_cmd
from app.cli.paw.commands import projects as projects_cmd
from app.cli.paw.commands import record as record_cmd
from app.cli.paw.commands import replay as replay_cmd
from app.cli.paw.commands import verify as verify_cmd
from app.cli.paw.commands import workspaces as workspaces_cmd

API_OVERRIDE_MARKER = "_PAW_CLI_API_OVERRIDE_ACTIVE"

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


app.add_typer(
    doctor_cmd.app,
    name="doctor",
    help="Health-check the persona + backend.",
)

app.add_typer(
    dev_cmd.app,
    name="dev",
    help="Dev backend process lifecycle (up/down/status).",
)

app.add_typer(
    project_cmd.app,
    name="project",
    help="Full local project lifecycle (frontend + backend).",
)

app.add_typer(
    project_cmd.env_app,
    name="env",
    help="Environment checks for CLI and local dev workflows.",
)

app.command("run")(project_cmd.run_project)
app.command("stop")(project_cmd.stop_project)

# login + logout sit at the top level (not under `paw auth`) so muscle memory
# matches gh/aws/gcloud. Re-register the underlying functions directly because
# typer.add_typer with name="" / name=None does not expose subcommands at root.
# No `help=` override — the function docstring carries the Examples block.
app.command("login")(login_cmd.login)
app.command("logout")(login_cmd.logout)

app.add_typer(
    auth_cmd.app,
    name="auth",
    help="Auth status.",
)

app.add_typer(
    admin_cmd.app,
    name="admin",
    help="Trusted local operator commands.",
)

app.add_typer(
    projects_cmd.app,
    name="projects",
    help="Manage projects.",
)

app.add_typer(
    personalization_cmd.app,
    name="profile",
    help="Read/update personalization profile.",
)

app.add_typer(
    appearance_cmd.app,
    name="appearance",
    help="Read/update appearance settings.",
)

# `conv` alias is a v2 follow-up; for now the canonical verb is `conversations`.
app.add_typer(
    conversations_cmd.app,
    name="conversations",
    help="Manage conversations and send chat turns.",
)

app.add_typer(
    workspaces_cmd.workspaces_app,
    name="workspaces",
    help="Manage workspaces (ls/show/use/create/rename/delete).",
)

app.add_typer(
    workspaces_cmd.workspace_app,
    name="workspace",
    help="Per-workspace env vars and files.",
)

app.add_typer(
    channels_cmd.app,
    name="channels",
    help="Telegram channel link/unlink.",
)

app.add_typer(
    mcp_cmd.app,
    name="mcp",
    help="MCP server registry CRUD.",
)

app.add_typer(
    plugins_cmd.app,
    name="plugins",
    help="Validate, inspect, and control dynamic plugins.",
)

app.add_typer(
    jobs_cmd.app,
    name="jobs",
    help="Scheduled jobs CRUD.",
)

app.add_typer(
    models_cmd.app,
    name="models",
    help="List available models.",
)

app.add_typer(
    completions_cmd.app,
    name="completions",
    help="Exercise composer completion endpoints.",
)

app.add_typer(
    messages_cmd.app,
    name="messages",
    help="Inspect persisted chat messages.",
)

app.add_typer(
    cost_cmd.app,
    name="cost",
    help="Cost summary + ledger.",
)

app.add_typer(
    audit_cmd.app,
    name="audit",
    help="Inspect audit events.",
)

app.add_typer(
    heartbeat_cmd.app,
    name="heartbeat",
    help="Sync HEARTBEAT.md scheduled checks.",
)

app.add_typer(
    lcm_cmd.app,
    name="lcm",
    help="LCM observability — pre-turn context inspection.",
)

app.add_typer(
    lab_cmd.app,
    name="lab",
    help="Exploratory benchmarks, run logs, and flow checklists.",
)

app.add_typer(
    api_cmd.app,
    name="api",
    help="Generic HTTP passthrough + OpenAPI discovery.",
)

app.add_typer(
    verify_cmd.app,
    name="verify",
    help="End-to-end provider verification scenarios.",
)

# `record` and `replay` accept arbitrary trailing args (the wrapped paw
# subcommand). Register them as plain commands so `ctx.args` carries
# everything after the flag set.
app.command(
    "record",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(record_cmd.record)
app.command(
    "replay",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(replay_cmd.replay)

# `fanout` re-invokes paw N times in parallel as subprocesses; the wrapped
# subcommand follows the slot count, so trailing args must pass through
# untouched (same pattern as record/replay above).
app.command(
    "fanout",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(fanout_cmd.fanout)

# `mirror` spawns the wrapped paw command against local + an upstream URL
# in parallel and diffs the SSE event streams to surface provider drift.
# Trailing args carry the wrapped subcommand verbatim, same as fanout.
app.command(
    "mirror",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(mirror_cmd.mirror)


@app.callback()
def _root(
    api: str | None = typer.Option(
        None,
        "--api",
        help="Backend base URL override for this invocation.",
    ),
) -> None:
    """Configure process-scoped options shared by every paw command."""
    if api:
        os.environ["PAW_BACKEND_URL"] = api
        os.environ[API_OVERRIDE_MARKER] = "1"
        return
    if os.environ.pop(API_OVERRIDE_MARKER, None):
        os.environ.pop("PAW_BACKEND_URL", None)


if __name__ == "__main__":
    app()

"""paw — top-level typer app. Subcommands register here."""

from __future__ import annotations

import typer

from app.cli.paw.commands import api as api_cmd
from app.cli.paw.commands import auth as auth_cmd
from app.cli.paw.commands import channels as channels_cmd
from app.cli.paw.commands import conversations as conversations_cmd
from app.cli.paw.commands import doctor as doctor_cmd
from app.cli.paw.commands import login as login_cmd
from app.cli.paw.commands import messages as messages_cmd
from app.cli.paw.commands import models as models_cmd
from app.cli.paw.commands import record as record_cmd
from app.cli.paw.commands import replay as replay_cmd
from app.cli.paw.commands import verify as verify_cmd
from app.cli.paw.commands import workspaces as workspaces_cmd

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
    models_cmd.app,
    name="models",
    help="List available models.",
)

app.add_typer(
    messages_cmd.app,
    name="messages",
    help="Inspect persisted chat messages.",
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


@app.callback()
def _root() -> None:
    """No-op root callback so subcommands attach cleanly."""


if __name__ == "__main__":
    app()

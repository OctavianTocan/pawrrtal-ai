"""paw — top-level typer app. Subcommands register here."""

from __future__ import annotations

import typer

from app.cli.paw.commands import auth as auth_cmd
from app.cli.paw.commands import conversations as conversations_cmd
from app.cli.paw.commands import doctor as doctor_cmd
from app.cli.paw.commands import login as login_cmd

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


@app.callback()
def _root() -> None:
    """No-op root callback so subcommands attach cleanly."""


if __name__ == "__main__":
    app()

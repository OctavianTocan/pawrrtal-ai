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

app.add_typer(
    doctor_cmd.app,
    name="doctor",
    help="Health-check the persona + backend.",
)


@app.callback()
def _root() -> None:
    """No-op root callback so subcommands attach cleanly."""


if __name__ == "__main__":
    app()

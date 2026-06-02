"""Top-level ``paw lab`` command group."""

from __future__ import annotations

import typer

from . import bench, flows, runs, telegram

app = typer.Typer(
    help="Exploratory benchmarks, run logs, and flow checklists.",
    no_args_is_help=True,
)

app.add_typer(bench.app, name="bench", help="Benchmark models and providers.")
app.add_typer(runs.app, name="runs", help="Inspect stored lab runs.")
app.add_typer(flows.app, name="flows", help="Inspect flow checklists.")
app.add_typer(telegram.app, name="telegram", help="Drive Telegram dogfood flows.")

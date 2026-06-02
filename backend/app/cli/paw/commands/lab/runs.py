"""Run-log commands for ``paw lab``."""

from __future__ import annotations

import json

import typer

from app.cli.paw.config import load_state
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows, require_one_output_mode

from .storage import list_runs, load_run

app = typer.Typer(help="Inspect stored lab runs.", no_args_is_help=True)


@app.command("ls")
def runs_ls(
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """List profile-scoped lab run logs."""
    require_one_output_mode(json_out=json_out, plain=plain)
    load_state(profile)
    rows = list_runs(profile)
    if json_out:
        emit_json(rows)
        return
    if plain:
        emit_plain_rows(
            (row["run_id"], row.get("kind") or "", row.get("model_id") or "") for row in rows
        )
        return
    for row in rows:
        emit_human(
            f"{row['run_id']}\t{row.get('kind') or ''}\t"
            f"{row.get('model_id') or ''}\t{row.get('created_at') or ''}"
        )


@app.command("show")
def runs_show(
    run_id: str = typer.Argument(...),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show one stored run log."""
    load_state(profile)
    payload = load_run(profile, run_id)
    if json_out:
        emit_json(payload)
        return
    emit_human(json.dumps(payload, indent=2, sort_keys=True))


@app.command("export")
def runs_export(
    run_id: str = typer.Argument(...),
    export_format: str = typer.Option("jsonl", "--format", help="jsonl or md."),
    profile: str = typer.Option("default", "--profile"),
) -> None:
    """Export one stored run as JSONL or Markdown."""
    load_state(profile)
    payload = load_run(profile, run_id)
    if export_format == "jsonl":
        emit_human(json.dumps(payload, sort_keys=True))
        return
    if export_format == "md":
        emit_human(_render_markdown(payload))
        return
    raise typer.BadParameter("--format must be jsonl or md")


def _render_markdown(payload: dict[str, object]) -> str:
    """Render a compact Markdown run report."""
    summary = payload.get("summary")
    lines = [
        f"# Paw Lab Run {payload.get('run_id')}",
        "",
        f"- Kind: {payload.get('kind')}",
        f"- Model: {payload.get('model_id')}",
        f"- Created: {payload.get('created_at')}",
        f"- Summary: `{json.dumps(summary, sort_keys=True)}`",
    ]
    return "\n".join(lines)

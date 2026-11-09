"""Tracked manual/semi-manual flow definitions for ``paw lab``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml

from app.cli.paw.errors import LocalError
from app.cli.paw.output import emit_human, emit_json

FLOW_DIR = Path(__file__).with_name("flow_defs")

app = typer.Typer(help="List and inspect Pawrrtal flow checklists.", no_args_is_help=True)


@app.command("ls")
def flows_ls(json_out: bool = typer.Option(False, "--json")) -> None:
    """List tracked flow definitions."""
    rows = [_flow_summary(flow) for flow in _load_flows()]
    if json_out:
        emit_json(rows)
        return
    for row in rows:
        emit_human(f"{row['id']}\t{row.get('title') or ''}")


@app.command("show")
def flows_show(
    flow_id: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show one flow definition by id."""
    flow = _load_flow(flow_id)
    if json_out:
        emit_json(flow)
        return
    emit_human(_render_flow(flow))


def _load_flows() -> list[dict[str, Any]]:
    """Load every YAML flow definition."""
    flows = [_load_yaml(path) for path in sorted(FLOW_DIR.glob("*.yaml"))]
    return [flow for flow in flows if flow]


def _load_flow(flow_id: str) -> dict[str, Any]:
    """Load one flow by id or raise a local error."""
    for flow in _load_flows():
        if flow.get("id") == flow_id:
            return flow
    raise LocalError(f"No lab flow found for id {flow_id}.")


def _load_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML flow file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LocalError(f"Flow file {path} must contain a mapping.")
    return data


def _flow_summary(flow: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": flow.get("id"),
        "title": flow.get("title"),
        "description": flow.get("description"),
    }


def _render_flow(flow: dict[str, Any]) -> str:
    lines = [
        f"{flow.get('id')}: {flow.get('title')}",
        "",
        str(flow.get("description") or ""),
        "",
        "Commands:",
    ]
    lines.extend(f"- {command}" for command in flow.get("commands") or [])
    return "\n".join(lines)

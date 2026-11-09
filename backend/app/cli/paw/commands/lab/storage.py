"""Run-log storage helpers for ``paw lab``."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.cli.paw.config import profile_dir
from app.cli.paw.errors import LocalError


def lab_dir(profile: str) -> Path:
    """Return the profile-scoped lab directory."""
    return profile_dir(profile) / "lab"


def runs_dir(profile: str) -> Path:
    """Return the directory containing JSON run logs."""
    return lab_dir(profile) / "runs"


def new_run_id(prefix: str) -> str:
    """Create a sortable run id with a short random suffix."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{prefix}-{uuid.uuid4().hex[:8]}"


def write_run(profile: str, payload: dict[str, Any]) -> Path:
    """Persist one run payload and return its JSON path."""
    run_id = str(payload.get("run_id") or new_run_id("run"))
    payload["run_id"] = run_id
    payload.setdefault("created_at", datetime.now(UTC).isoformat())
    directory = runs_dir(profile)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return path


def load_run(profile: str, run_id: str) -> dict[str, Any]:
    """Load one run payload by id."""
    path = runs_dir(profile) / f"{run_id}.json"
    if not path.exists():
        raise LocalError(f"No lab run found for id {run_id}.")
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise LocalError(f"Lab run {run_id} is malformed.")
    return body


def list_runs(profile: str) -> list[dict[str, Any]]:
    """Return compact summaries for every stored run, newest first."""
    directory = runs_dir(profile)
    if not directory.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(body, dict):
            continue
        rows.append(
            {
                "run_id": body.get("run_id") or path.stem,
                "kind": body.get("kind"),
                "created_at": body.get("created_at"),
                "model_id": body.get("model_id"),
                "summary": body.get("summary") or {},
                "path": str(path),
            }
        )
    return rows

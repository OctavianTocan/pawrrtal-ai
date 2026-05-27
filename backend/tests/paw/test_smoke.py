"""Smoke tests for the paw CLI skeleton + doctor."""

from __future__ import annotations

import json

from app.cli.paw.main import app


def test_paw_help_runs(runner):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Pawrrtal Agent CLI" in result.stdout


def test_paw_doctor_runs_without_state(runner):
    """No state file yet — doctor still runs, exits 6."""
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 6
    out = json.loads(result.stdout)
    assert out["passed"] is False
    names = {c["name"] for c in out["checks"]}
    assert "state_file_exists" in names

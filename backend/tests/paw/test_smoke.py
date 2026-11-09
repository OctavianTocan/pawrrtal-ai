"""Smoke tests for the paw CLI skeleton + doctor."""

from __future__ import annotations

import json

import httpx
import respx

from app.cli.paw.config import ENV_BASE_URLS
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


def test_global_api_option_targets_one_invocation(runner):
    """Top-level ``--api`` lets any command target an arbitrary instance."""
    backend = "http://target-instance"
    with respx.mock(base_url=backend, assert_all_called=False) as r:
        health = r.get("/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        result = runner.invoke(app, ["--api", backend, "doctor", "--json"])

    assert result.exit_code == 6
    assert health.called
    out = json.loads(result.stdout)
    backend_check = next(c for c in out["checks"] if c["name"] == "backend_reachable")
    assert backend_check["passed"] is True
    assert backend_check["detail"] == f"{backend} -> 200"


def test_prod_env_uses_owned_hostname() -> None:
    """The built-in prod alias must not point at an unowned domain."""
    assert ENV_BASE_URLS["prod"] == "https://pawrrtal.octaviantocan.com"

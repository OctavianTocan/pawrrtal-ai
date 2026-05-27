"""Live E2E: ``paw verify codex`` against the booted backend.

Skips if ``~/.codex/auth.json`` is missing because the Codex provider
needs a real Codex session to proxy through.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("PAW_E2E") != "1",
    reason="Set PAW_E2E=1 to run live paw tests",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
PAW_SUBPROCESS_TIMEOUT_SECONDS = 300.0


def test_verify_codex_live(logged_in_paw: str, isolated_paw_config: Path) -> None:
    """Run ``paw verify codex --json`` end-to-end against the live backend."""
    if not (Path.home() / ".codex" / "auth.json").exists():
        pytest.skip("~/.codex/auth.json missing; skipping live codex verify")

    result = subprocess.run(
        ["uv", "run", "paw", "verify", "codex", "--json"],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "PAW_CONFIG_DIR": str(isolated_paw_config)},
        capture_output=True,
        text=True,
        timeout=PAW_SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, (
        f"verify codex failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert payload["passed"] is True

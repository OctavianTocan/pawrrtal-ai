"""Live E2E: ``paw verify chat-roundtrip`` against the booted backend.

Uses a LiteLLM-routed model (cheap, deterministic) so this test doesn't
need Codex credentials. When ``OPENAI_API_KEY`` is unset the test skips
because LiteLLM can't reach OpenAI without it.
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
PAW_SUBPROCESS_TIMEOUT_SECONDS = 180.0


def test_chat_roundtrip_live(logged_in_paw: str, isolated_paw_config: Path) -> None:
    """Run ``paw verify chat-roundtrip --json`` end-to-end against the live backend."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set; skipping live chat-roundtrip")

    result = subprocess.run(
        [
            "uv",
            "run",
            "paw",
            "verify",
            "chat-roundtrip",
            "--model",
            "litellm:openai/gpt-4o-mini",
            "--json",
        ],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "PAW_CONFIG_DIR": str(isolated_paw_config)},
        capture_output=True,
        text=True,
        timeout=PAW_SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, (
        f"verify chat-roundtrip failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    failed = [check for check in payload["checks"] if not check["passed"]]
    assert not failed, f"failing checks: {failed}"

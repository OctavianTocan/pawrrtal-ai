"""Live-backend E2E fixtures for paw. Gated on ``PAW_E2E=1``.

Boots a real uvicorn subprocess pointing at ``main:app`` with a throwaway
in-memory SQLite database, waits for the ``/api/v1/health`` endpoint to
respond, and exposes helpers for running ``paw`` CLI subprocesses against
the live backend. The whole module is skipped unless the gate is set so
the default test run stays offline.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

# The ``PAW_E2E=1`` gate is enforced at two layers:
#
# 1. ``tests/conftest.py`` adds ``e2e_paw/*`` to ``collect_ignore_glob`` when
#    the env var is unset, so a plain ``uv run pytest`` never imports this
#    file. That's the primary, fast path.
# 2. Each test module in this package re-checks the gate with
#    ``pytestmark = pytest.mark.skipif(...)`` so that explicitly targeting
#    the directory without the gate (``pytest tests/e2e_paw/``) still skips
#    cleanly instead of trying to boot uvicorn.
#
# A ``pytest.skip(allow_module_level=True)`` here would surface as a
# collection error rather than a skip — that flag is only valid in test
# modules, not conftest — so the per-module marker is the correct seam.

HEALTH_TIMEOUT_SECONDS = 60.0
HEALTH_POLL_INTERVAL_SECONDS = 0.25
HEALTH_REQUEST_TIMEOUT_SECONDS = 2.0
TERMINATE_GRACE_SECONDS = 10.0
KILL_GRACE_SECONDS = 5.0
PAW_SUBPROCESS_TIMEOUT_SECONDS = 180.0

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    """Return a TCP port the OS just bound and released — race window is small enough for tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_health(url: str, timeout: float) -> None:
    """Poll ``url`` until it returns 200 or the deadline elapses."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=HEALTH_REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return
        except httpx.RequestError as exc:
            last_err = exc
        time.sleep(HEALTH_POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        f"Backend at {url} did not become healthy in {timeout}s; last_err={last_err!r}",
    )


@pytest.fixture(scope="session")
def live_backend(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Boot uvicorn against ``main:app`` with a throwaway DB; tear down on session exit."""
    port = _free_port()
    # Use a tmpdir-backed SQLite file rather than ``:memory:`` because the
    # backend opens multiple connections (FastAPI-Users, app code, etc.) and
    # ``sqlite+aiosqlite:///:memory:`` without ``StaticPool`` gives each
    # connection its own private in-memory DB — schema appears on connection
    # A but not connection B, and lookups fail with "no such table: user".
    # A real file path makes all connections see the same DB.
    db_path = tmp_path_factory.mktemp("paw-e2e-db") / "live.sqlite"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "ADMIN_EMAIL": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
        "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD", "supersecret"),
    }
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=sys.stderr,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(f"{base_url}/api/v1/health", timeout=HEALTH_TIMEOUT_SECONDS)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=KILL_GRACE_SECONDS)


@pytest.fixture
def isolated_paw_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test gets a fresh ``$PAW_CONFIG_DIR`` so paw state doesn't leak between tests."""
    cfg = tmp_path / "paw-config"
    cfg.mkdir(parents=True)
    monkeypatch.setenv("PAW_CONFIG_DIR", str(cfg))
    return cfg


@pytest.fixture
def logged_in_paw(live_backend: str, isolated_paw_config: Path) -> str:
    """Run ``paw login --dev-admin`` against the live backend and return the base URL."""
    result = subprocess.run(
        ["uv", "run", "paw", "login", "--dev-admin", "--api", live_backend, "--json"],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "PAW_CONFIG_DIR": str(isolated_paw_config)},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"paw login --dev-admin failed:\nstdout={result.stdout}\nstderr={result.stderr}",
        )
    return live_backend


@pytest.fixture
def run_paw(isolated_paw_config: Path) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    """Helper that runs ``paw`` with the isolated config dir and returns the completed process."""

    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "run", "paw", *args],
            cwd=str(BACKEND_DIR),
            env={**os.environ, "PAW_CONFIG_DIR": str(isolated_paw_config)},
            capture_output=True,
            text=True,
            timeout=PAW_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )

    return _run

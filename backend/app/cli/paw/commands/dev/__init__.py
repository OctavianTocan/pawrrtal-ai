"""paw dev — local backend process lifecycle (up/down/status).

``paw dev`` is a local CLI orchestrator, not a backend feature. It manages
a long-lived ``uvicorn`` subprocess running the FastAPI app. The PID,
port, start timestamp, and log path are persisted in a small JSON state
file under ``<PAW_CONFIG_DIR>/<profile>/dev.json`` so subsequent ``paw
dev`` invocations can locate the process.

This is intentionally minimal — think of it as a tiny ``pm2`` for the
pawrrtal backend so verify suites can self-bootstrap when the backend
isn't already running. It coexists with ``just dev`` (which boots
frontend + backend together via ``dev.ts``) but does not supersede it:
``just dev`` remains the canonical full-stack dev loop. ``paw dev``
targets the backend only and is the right tool for headless agent /
verify scenarios.

Example::

    paw dev up                 # boot backend on 127.0.0.1:8000 in the background
    paw dev status --json      # check PID + health
    paw dev down               # SIGTERM then SIGKILL after grace period

Package layout:

* ``state``    — persisted JSON record (``DevState``, ``load_state`` / ``save_state``).
* ``process``  — uvicorn spawn + signal helpers + ``/api/v1/health`` probe.
* ``commands`` — Typer surface (``up`` / ``down`` / ``status``) that wires
  the other two together.
"""

from __future__ import annotations

from app.cli.paw.commands.dev.commands import app
from app.cli.paw.commands.dev.state import DEV_STATE_SCHEMA_VERSION

__all__ = ["DEV_STATE_SCHEMA_VERSION", "app"]

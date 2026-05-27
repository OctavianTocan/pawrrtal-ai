"""Live-backend E2E tests for the paw CLI.

This package is opt-in via the ``PAW_E2E=1`` environment variable. Without
the gate, every test in this directory skips at module import time so a
plain ``uv run pytest`` collection stays fast and offline. Set
``PAW_E2E=1`` to boot a real uvicorn subprocess and run paw against it.
"""

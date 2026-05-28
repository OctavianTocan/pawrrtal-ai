"""Startup hook: Gemini CLI availability probe.

Emits a single log line at boot describing whether the ``gemini`` binary
is on ``$PATH``. The Gemini CLI provider (``host=Host.gemini_cli`` models)
needs the binary to function; the rest of Pawrrtal does not, so we never
block startup — operators see the warning and decide.

Order 15: between tracing (10) and database init (20). Cheap probe, no
external dependencies; running it early surfaces the warning before any
chat turn would otherwise hit a confusing per-request spawn failure.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from app.core.providers.gemini_cli import GEMINI_BINARY_NAME, is_gemini_cli_available
from app.infrastructure.lifecycle import startup_hook

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


@startup_hook(order=15)
async def log_gemini_cli_status(app: FastAPI) -> None:
    """Log whether the Gemini CLI binary is discoverable on ``$PATH``."""
    del app  # unused — every startup hook receives the app but this one doesn't need it
    if not is_gemini_cli_available():
        logger.warning(
            "GEMINI_CLI_UNAVAILABLE binary=%s path=$PATH "
            "(install with `npm install -g @google/gemini-cli` to enable "
            "gemini-cli:* models; other providers unaffected)",
            GEMINI_BINARY_NAME,
        )
        return
    logger.info("GEMINI_CLI_FOUND path=%s", shutil.which(GEMINI_BINARY_NAME))

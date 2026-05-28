# logger_setup.py
"""Global logging configuration.

Writes to ``backend/app.log`` (resolved relative to this file, not the
process CWD) so logs always land in the same place regardless of where
``uvicorn`` is launched from. The previous implementation passed a
relative ``"app.log"`` path to :class:`logging.FileHandler`, which silently
split logs across two files (``backend/app.log`` when run from ``backend/``,
project-root ``app.log`` when run from the monorepo root via ``just dev``).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Resolve <repo>/backend/app.log regardless of process CWD.
# logger_setup.py lives at backend/app/logger_setup.py, so parent.parent == backend/.
_LOG_FILE_PATH = Path(__file__).resolve().parent.parent / "app.log"

# Cap log file at ~10MB and keep 5 rotations so the log directory does not grow unbounded.
_LOG_MAX_BYTES = 10 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

# Third-party loggers that emit DEBUG-level chatter on every HTTP/2 frame and
# completely drown out our application logs. Cap them at INFO (or higher) so
# the file remains readable when looking for app-level events.
_NOISY_THIRD_PARTY_LOGGERS: dict[str, int] = {
    "hpack": logging.WARNING,
    "hpack.hpack": logging.WARNING,
    "hpack.table": logging.WARNING,
    "httpcore": logging.INFO,
    "httpcore.http2": logging.INFO,
    "httpcore.http11": logging.INFO,
    "httpcore.connection": logging.INFO,
    "httpx": logging.INFO,
    "asyncio": logging.INFO,
    "watchfiles": logging.INFO,
    "urllib3": logging.INFO,
    "LiteLLM": logging.ERROR,
    "litellm": logging.ERROR,
}


def configure_logging() -> None:
    """Set up the global logging configuration.

    Configures the root logger so every module-level logger inherits the
    same handlers. Console handler stays at INFO; file handler captures
    DEBUG to give us full fidelity when investigating issues.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 1. Console Handler (for terminal output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
    console_handler.setFormatter(console_format)

    # 2. Rotating File Handler — pinned to backend/app.log regardless of CWD.
    file_handler = RotatingFileHandler(
        _LOG_FILE_PATH,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    # Millisecond timestamps + thread name make it possible to distinguish
    # near-simultaneous requests (e.g. a duplicate POST fired by the client).
    file_format = logging.Formatter(
        "%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s - [%(threadName)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    # Prevent adding handlers multiple times if configure_logging is called twice.
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    # Quiet noisy third-party loggers so app-level events stay legible.
    for logger_name, level in _NOISY_THIRD_PARTY_LOGGERS.items():
        logging.getLogger(logger_name).setLevel(level)

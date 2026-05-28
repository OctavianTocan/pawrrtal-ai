"""``paw mirror`` — local vs upstream diff orchestrator.

Public surface is the ``mirror`` typer callable; the rest is internal to
the package and may be reshaped without affecting the CLI.
"""

from __future__ import annotations

from app.cli.paw.commands.mirror.cli import mirror

__all__ = ["mirror"]

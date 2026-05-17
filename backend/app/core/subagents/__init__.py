"""Subagent system: personas, registry, runner.

Public surface kept narrow on purpose — most callers only need the
persona resolver and the constants module.  The runner + registry are
loaded by ``app.core.tools.subagents_agent`` (PR 4) and by the
conversation-delete cascade (PR 2); they're not part of the import
surface that other features should reach for.
"""

from app.core.subagents.persona import (
    KNOWN_TOOL_NAMES,
    Persona,
    PersonaError,
    list_builtin_personas,
    load_builtin_personas,
    resolve_persona,
)

__all__ = [
    "KNOWN_TOOL_NAMES",
    "Persona",
    "PersonaError",
    "list_builtin_personas",
    "load_builtin_personas",
    "resolve_persona",
]

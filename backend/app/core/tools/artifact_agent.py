"""AgentTool wrapper for the ``render_artifact`` core.

Builds the :class:`AgentTool` consumed by ``app.core.agent_tools``.  The
JSON Schema below is what the LLM sees in its tool catalogue, so the
descriptions are written *for the model*: explicit about when to call
this, what shapes are valid, and what NOT to do.

Architecture note
-----------------

The execute callback returns the LLM-facing summary string.  It does
**not** carry the spec back to the loop — the chat router lifts the spec
out of the tool's ``arguments`` (which the LLM already provided) and
emits a sibling SSE event.  See module docstring in
:mod:`app.core.tools.artifact` for the full wire shape.
"""

from __future__ import annotations

from typing import Any

from app.core.agent_loop.types import AgentTool

# Re-export artifact helpers so callers (e.g. app.api.chat) only need
# one internal import instead of two, keeping that file under the fan-out
# budget enforced by sentrux's no_god_files rule. ``__all__`` makes
# these public re-exports for mypy without tripping ruff's PLC0414.
from app.core.tools.artifact import (
    ArtifactValidationError,
    build_artifact,
    llm_summary_for,
)

ARTIFACT_TOOL_NAME = "render_artifact"

_ARTIFACT_TOOL_DESCRIPTION = (
    "Render a structured 'artifact' inline in the user's chat — a small "
    "preview card the user can click to expand into a full-screen viewer. "
    "Use this when a structured shape (comparison table, dashboard, "
    "labelled stat row, side-by-side rename, numbered explanation list) "
    "communicates an answer better than prose. Do NOT use it for plain "
    "text replies — write those directly. Each call surfaces ONE artifact; "
    "call again only if the user asks for another. The catalog of allowed "
    "components is enforced client-side; unknown component names will "
    "render a placeholder."
)

# Generic dict schema — we deliberately don't enumerate the catalog here,
# so adding components on the frontend doesn't require a backend change.
# The frontend renderer is the source of truth and falls back gracefully
# on unknown component names.
_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "json-render flat-spec object. Top-level shape: "
        "{ 'root': '<id>', 'elements': { '<id>': { 'type': "
        "'<ComponentName>', 'props': {...}, 'children': ['<id>', ...] } } }. "
        "The 'root' string must be a key in 'elements'. Children are "
        "string ids referring to other elements in the same map. Component "
        "names available client-side (current catalog): Page, Section, "
        "Heading, Paragraph, CardRow, BeforeAfter, ColumnList, BucketList, "
        "Bucket, RouteTable, RiskGrid, Steps, StatPill, Footer."
    ),
    "properties": {
        "root": {
            "type": "string",
            "description": "Id of the root element to render.",
        },
        "elements": {
            "type": "object",
            "description": (
                "Map of element id → element object. Each element has {type, props, children?}."
            ),
        },
    },
    "required": ["root", "elements"],
}

_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": (
                "Short title shown on the preview card and the expanded "
                "viewer. ≤200 chars. Pick something a human would skim "
                "and recognise."
            ),
        },
        "spec": _SPEC_SCHEMA,
    },
    "required": ["title", "spec"],
}


def make_artifact_tool() -> AgentTool:
    """Return the :class:`AgentTool` for ``render_artifact``."""

    async def _execute(tool_call_id: str, **kwargs: object) -> str:
        title = str(kwargs.get("title") or "")
        spec = kwargs.get("spec")
        if not isinstance(spec, dict):
            return (
                "Error: 'spec' must be an object with 'root' and 'elements' "
                "keys. The artifact was NOT rendered. Call render_artifact "
                "again with a corrected spec."
            )
        try:
            payload = build_artifact(title=title, spec=spec)
        except ArtifactValidationError as exc:
            return (
                f"Error: artifact spec rejected — {exc}. The artifact was "
                "NOT rendered. Correct the spec and call render_artifact "
                "again."
            )
        return llm_summary_for(payload)

    return AgentTool(
        name=ARTIFACT_TOOL_NAME,
        description=_ARTIFACT_TOOL_DESCRIPTION,
        parameters=_PARAMETERS,
        execute=_execute,
    )


__all__ = [
    "ARTIFACT_TOOL_NAME",
    "ArtifactValidationError",
    "build_artifact",
    "llm_summary_for",
    "make_artifact_tool",
]

"""AgentTool wrapper for the ``render_artifact`` core.

Builds the :class:`AgentTool` consumed by ``app.agents.tools``.  The
JSON Schema below is what the LLM sees in its tool catalogue, so the
descriptions are written *for the model*: explicit about when to call
this, what shapes are valid, and what NOT to do.

Architecture note
-----------------

The execute callback returns the LLM-facing summary string.  It does
**not** carry the spec back to the loop — the chat router lifts the spec
out of the tool's ``arguments`` (which the LLM already provided) and
emits a sibling SSE event.  See module docstring in
:mod:`app.tools.artifact` for the full wire shape.
"""

from __future__ import annotations

from typing import Any

from app.agents.types import AgentTool

# Re-export artifact helpers so callers (e.g. app.chat.router) only need
# one internal import instead of two, keeping that file under the fan-out
# budget enforced by sentrux's no_god_files rule. ``__all__`` makes
# these public re-exports for mypy without tripping ruff's PLC0414.
from app.tools.artifact import (
    ArtifactValidationError,
    build_artifact,
    llm_summary_for,
)
from app.tools.display import make_tool_display, summarize_title

ARTIFACT_TOOL_NAME = "render_artifact"

# Surfaces whose frontend can render the interactive widget catalog. Telegram
# (and any other surface that falls back to plain text) only sees the
# read-only components — telling the model otherwise would invite it to emit
# widgets that vanish into a text-rendered card.
_INTERACTIVE_SURFACES: frozenset[str] = frozenset({"web", "electron"})

_READ_ONLY_CATALOG = (
    "Page, Section, Heading, Paragraph, CardRow, BeforeAfter, ColumnList, "
    "BucketList, Bucket, RouteTable, RiskGrid, Steps, StatPill"
)

_INTERACTIVE_CATALOG = (
    "ActionButton (click → user message), ChoiceGroup (single or multi-select → "
    "user message), TextField (free text → user message), NumberField "
    "(numeric slider/input → user message)"
)

_BASE_DESCRIPTION = (
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

_INTERACTIVE_DESCRIPTION_SUFFIX = (
    " The current surface supports INTERACTIVE artifacts: include one or "
    "more of the interactive components from the catalog when you want the "
    "user to respond by clicking, choosing, typing, or picking a number. "
    "The user's interaction arrives as a regular follow-up user message in "
    "the next turn — read it like any other input. Keep interactive widgets "
    "purposeful (one decision per artifact); do not stack many buttons just "
    "because you can."
)


def _build_spec_schema(*, surface: str | None) -> dict[str, Any]:
    """Return the spec JSONSchema, enumerating the catalog the surface supports."""
    catalog = _READ_ONLY_CATALOG
    if surface in _INTERACTIVE_SURFACES:
        catalog = f"{_READ_ONLY_CATALOG}, {_INTERACTIVE_CATALOG}"
    return {
        "type": "object",
        "description": (
            "json-render flat-spec object. Top-level shape: "
            "{ 'root': '<id>', 'elements': { '<id>': { 'type': "
            "'<ComponentName>', 'props': {...}, 'children': ['<id>', ...] } } }. "
            "The 'root' string must be a key in 'elements'. Children are "
            "string ids referring to other elements in the same map. Component "
            f"names available client-side (current catalog): {catalog}."
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


def _build_parameters(*, surface: str | None) -> dict[str, Any]:
    """Build the JSON Schema for the tool's arguments."""
    return {
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
            "spec": _build_spec_schema(surface=surface),
        },
        "required": ["title", "spec"],
    }


def _build_description(*, surface: str | None) -> str:
    """Append the interactive blurb only on surfaces that can render it."""
    if surface in _INTERACTIVE_SURFACES:
        return _BASE_DESCRIPTION + _INTERACTIVE_DESCRIPTION_SUFFIX
    return _BASE_DESCRIPTION


def make_artifact_tool(*, surface: str | None = None) -> AgentTool:
    """Return the :class:`AgentTool` for ``render_artifact``.

    Args:
        surface: Channel surface ("web", "electron", "telegram", ...).
            Web/electron get the interactive component catalog in the tool
            description; everything else gets the read-only catalog. The
            execute callback and validation are surface-independent — the
            gating is purely advisory text so the model emits widgets only
            on surfaces that can render them.
    """

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
        description=_build_description(surface=surface),
        parameters=_build_parameters(surface=surface),
        execute=_execute,
        display=make_tool_display(
            icon="🧩",
            label="Render Artifact",
            present=lambda args: (
                f"🧩 Rendering artifact {summarize_title(args.get('title'), 'preview')}"
            ),
            compact=lambda args: (
                f"Render artifact -> {summarize_title(args.get('title'), 'preview')}"
            ),
        ),
    )


__all__ = [
    "ARTIFACT_TOOL_NAME",
    "ArtifactValidationError",
    "build_artifact",
    "llm_summary_for",
    "make_artifact_tool",
]

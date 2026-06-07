"""Agent tool for searching installed plugin capabilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.types import AgentTool
from app.plugins.capability_catalog import CapabilityRecord, CapabilitySearch
from app.plugins.errors import PluginError
from app.plugins.host import get_plugin_host
from app.plugins.registry import ContributionRegistrySnapshot, PluginLoadOutcome


def make_search_plugin_capabilities_tool(*, workspace_root: Path) -> AgentTool:
    """Return a tool that lets the agent inspect active plugin capabilities."""

    async def execute(tool_call_id: str, **kwargs: Any) -> str:
        query = _coerce_str(kwargs.get("query"))
        capability_type = _coerce_str(kwargs.get("type"))
        slot = _coerce_str(kwargs.get("slot"))
        intent = _coerce_str(kwargs.get("intent"))
        tag = _coerce_str(kwargs.get("tag"))
        plugin_id = _coerce_str(kwargs.get("plugin_id"))
        permission = _coerce_str(kwargs.get("permission"))
        include_unavailable = _coerce_bool(kwargs.get("include_unavailable"))
        limit = _coerce_limit(kwargs.get("limit"))
        try:
            _previous, snapshot = get_plugin_host().reload(workspace_root=workspace_root)
        except PluginError as exc:
            return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

        filters = CapabilitySearch(
            query=query,
            capability_type=capability_type,
            intent=intent,
            slot=slot,
            tag=tag,
            plugin_id=plugin_id,
            permission=permission,
            include_unavailable=include_unavailable,
        )
        preferences = _slot_preferences(snapshot, slot) if slot else ()
        rows = [
            _capability_row(
                capability=capability,
                outcome=snapshot.outcome_for(capability.plugin_id),
                preferred=capability.key in preferences,
            )
            for capability in snapshot.capability_catalog().search(
                filters,
                slot_preferences=preferences,
            )
        ]
        payload = {
            "success": True,
            "workspace_root": str(workspace_root),
            "snapshot_fingerprint": snapshot.fingerprint,
            "count": len(rows),
            "capabilities": rows[:limit],
            "truncated": len(rows) > limit,
        }
        return json.dumps(payload, ensure_ascii=False)

    return AgentTool(
        name="search_plugin_capabilities",
        description=(
            "Search installed and enabled Pawrrtal plugin capabilities for this workspace. "
            "Use this before assuming which optional tool, provider, channel, context provider, "
            "or slot candidate exists. Set include_unavailable=true to inspect disabled, "
            "misconfigured, or validation-blocked plugins."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search."},
                "type": {
                    "type": "string",
                    "description": "Capability type, such as cli_tool, provider, channel, or turn_context_provider.",
                },
                "slot": {
                    "type": "string",
                    "description": "Slot id, such as web_search, turn_context, or workspace_knowledge.",
                },
                "intent": {"type": "string", "description": "Intent id to match."},
                "tag": {"type": "string", "description": "Tag to match."},
                "plugin_id": {"type": "string", "description": "Specific plugin id."},
                "permission": {"type": "string", "description": "Required permission to match."},
                "include_unavailable": {
                    "type": "boolean",
                    "description": "Include disabled, misconfigured, failed, or validation-blocked capabilities.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return, from 1 to 50.",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 20,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
        execute=execute,
    )


def _capability_row(
    *,
    capability: CapabilityRecord,
    outcome: PluginLoadOutcome | None,
    preferred: bool,
) -> dict[str, object]:
    """Return a capability row enriched with plugin load status."""
    row = capability.to_wire(preferred=preferred)
    row["plugin_status"] = outcome.status if outcome else "unknown"
    row["plugin_reason"] = outcome.reason if outcome else None
    row["missing_env"] = list(outcome.missing_env) if outcome else []
    return row


def _slot_preferences(
    snapshot: ContributionRegistrySnapshot,
    slot_id: str,
) -> tuple[str, ...]:
    """Collect ordered slot preferences from active plugin state files."""
    preferences: list[str] = []
    for outcome in snapshot.outcomes:
        preferences.extend(outcome.state.slot_preference_keys(slot_id))
    return tuple(dict.fromkeys(preferences))


def _coerce_str(value: object) -> str | None:
    """Coerce optional string arguments."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _coerce_bool(value: object) -> bool:
    """Coerce a JSON boolean argument."""
    return value is True


def _coerce_limit(value: object) -> int:
    """Coerce and clamp the result limit."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 20
    return max(1, min(value, 50))

"""Searchable capability catalog built from plugin snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from app.plugins.contributions import Capability
from app.plugins.manifest import PluginManifest

CapabilityState = Literal[
    "enabled",
    "disabled",
    "needs_validation",
    "misconfigured",
    "failed",
    "blocked_by_dependency",
]


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    """One normalized capability row in the plugin catalog."""

    plugin_id: str
    capability_id: str
    type: str
    title: str
    description: str
    tags: tuple[str, ...]
    intents: tuple[str, ...]
    slots: tuple[str, ...]
    state: CapabilityState
    priority: int
    exposure: str
    permissions: tuple[str, ...]
    requires_confirmation: bool
    input_schema: dict[str, object]
    examples: tuple[dict[str, object], ...]
    invokable: bool = True

    @property
    def key(self) -> str:
        """Return the stable composite key used for preferences and invocation."""
        return f"{self.plugin_id}/{self.capability_id}"

    @classmethod
    def from_capability(
        cls,
        *,
        plugin_id: str,
        capability: Capability,
        state: CapabilityState = "enabled",
    ) -> CapabilityRecord:
        """Build a catalog row from manifest capability metadata."""
        return cls(
            plugin_id=plugin_id,
            capability_id=capability.id,
            type=capability.type,
            title=capability.title or capability.id.replace("_", " ").title(),
            description=capability.description,
            tags=capability.tags,
            intents=capability.intents,
            slots=capability.slots,
            state=state,
            priority=capability.priority,
            exposure=capability.exposure,
            permissions=tuple(capability.permissions),
            requires_confirmation=capability.requires_confirmation,
            input_schema=_input_schema(capability),
            examples=capability.examples,
            invokable=capability.type in {"cli_tool", "python_tool"}
            and capability.exposure in {"direct", "direct_and_catalog"},
        )

    def to_wire(self, *, preferred: bool = False) -> dict[str, object]:
        """Return a JSON-serializable catalog row."""
        return {
            "plugin_id": self.plugin_id,
            "capability_id": self.capability_id,
            "key": self.key,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "intents": list(self.intents),
            "slots": list(self.slots),
            "state": self.state,
            "preferred": preferred,
            "priority": self.priority,
            "exposure": self.exposure,
            "permissions": list(self.permissions),
            "requires_confirmation": self.requires_confirmation,
            "input_schema": self.input_schema,
            "examples": list(self.examples),
            "invokable": self.invokable,
        }


@dataclass(frozen=True, slots=True)
class CapabilitySearch:
    """Filters used for capability catalog search."""

    query: str | None = None
    capability_type: str | None = None
    intent: str | None = None
    slot: str | None = None
    tag: str | None = None
    plugin_id: str | None = None
    permission: str | None = None
    include_unavailable: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityCatalog:
    """Immutable searchable catalog for plugin capabilities."""

    capabilities: tuple[CapabilityRecord, ...]

    @classmethod
    def from_manifests(cls, manifests: tuple[PluginManifest, ...]) -> CapabilityCatalog:
        """Build a catalog from manifests with composite capability identities."""
        records: list[CapabilityRecord] = []
        seen: set[str] = set()
        for manifest in manifests:
            for capability in manifest.capabilities:
                record = CapabilityRecord.from_capability(
                    plugin_id=manifest.id,
                    capability=capability,
                )
                if record.key in seen:
                    raise ValueError(f"Duplicate capability key: {record.key}")
                seen.add(record.key)
                records.append(record)
        return cls(capabilities=tuple(records))

    def search(
        self,
        filters: CapabilitySearch,
        *,
        slot_preferences: tuple[str, ...] = (),
    ) -> tuple[CapabilityRecord, ...]:
        """Return catalog rows matching filters, sorted for agent selection."""
        preference_index = {key: index for index, key in enumerate(slot_preferences)}
        rows = [row for row in self.capabilities if _matches(row, filters)]
        return tuple(sorted(rows, key=lambda row: _sort_key(row, preference_index)))

    def describe(self, *, plugin_id: str, capability_id: str) -> CapabilityRecord | None:
        """Return one capability by composite identity."""
        for capability in self.capabilities:
            if capability.plugin_id == plugin_id and capability.capability_id == capability_id:
                return capability
        return None

    def fingerprint(self) -> str:
        """Return a stable hash for catalog contents."""
        payload = [capability.to_wire() for capability in self.capabilities]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _input_schema(capability: Capability) -> dict[str, object]:
    """Return the capability's invocation input schema."""
    args_schema = getattr(capability, "args_schema", None)
    if isinstance(args_schema, dict):
        return args_schema
    return {}


def _matches(row: CapabilityRecord, filters: CapabilitySearch) -> bool:
    """Return whether one capability row satisfies search filters."""
    checks = (
        filters.include_unavailable or row.state == "enabled",
        filters.capability_type is None or row.type == filters.capability_type,
        filters.intent is None or filters.intent in row.intents,
        filters.slot is None or filters.slot in row.slots,
        filters.tag is None or filters.tag in row.tags,
        filters.plugin_id is None or row.plugin_id == filters.plugin_id,
        filters.permission is None or filters.permission in row.permissions,
        filters.query is None or _query_matches(row, filters.query),
    )
    return all(checks)


def _query_matches(row: CapabilityRecord, query: str) -> bool:
    """Return whether a free-text query matches a capability."""
    haystack = " ".join(
        (
            row.key,
            row.title,
            row.description,
            *row.tags,
            *row.intents,
            *row.slots,
        )
    )
    return query.lower() in haystack.lower()


def _sort_key(
    row: CapabilityRecord,
    preference_index: dict[str, int],
) -> tuple[int, int, int, str]:
    """Sort by workspace preference, health, manifest priority, then stable key."""
    preferred = preference_index.get(row.key, len(preference_index))
    health_rank = 0 if row.state == "enabled" else 1
    return (preferred, health_rank, -row.priority, row.key)

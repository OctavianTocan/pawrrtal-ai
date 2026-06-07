"""Tests for dynamic plugin manifest validation."""

from __future__ import annotations

from typing import cast

import pytest

from app.plugins.capability_catalog import CapabilityCatalog, CapabilitySearch
from app.plugins.errors import PluginManifestError
from app.plugins.manifest import validate_plugin_manifest


def _valid_manifest() -> dict[str, object]:
    """Return a plan-shaped manifest with representative safe capabilities."""
    return {
        "schema_version": 1,
        "id": "search_pack",
        "name": "Search Pack",
        "version": "1.0.0",
        "description": "Search tools for the Paw workspace.",
        "enabled_by_default": False,
        "permissions": ["subprocess", "secrets"],
        "env": [
            {
                "name": "SEARCH_API_KEY",
                "inject_as": "SEARCH_TOKEN",
                "required": True,
                "scope": "workspace",
                "overridable": True,
                "gateway_fallback": False,
                "secret": True,
                "label": "Search API Key",
                "description": "Token used by the search CLI.",
            }
        ],
        "capabilities": [
            {
                "type": "cli_tool",
                "id": "web_search",
                "tool_name": "web_search",
                "title": "Web Search",
                "description": "Search the public web with a configured CLI.",
                "tags": ["search"],
                "intents": ["web.search"],
                "slots": ["web_search"],
                "priority": 10,
                "exposure": "catalog",
                "permissions": ["secrets"],
                "entrypoint": ["search-agent", "--json"],
                "args_schema": {"type": "object"},
            },
            {
                "type": "settings",
                "id": "search_settings",
                "title": "Search Settings",
                "description": "Settings metadata for search credentials.",
            },
            {
                "type": "skill",
                "id": "search_skill",
                "title": "Search Skill",
                "description": "Skill that teaches search tool usage.",
                "path": "skills/search/SKILL.md",
            },
            {
                "type": "agent_profile",
                "id": "researcher_profile",
                "title": "Researcher",
                "description": "Research-focused agent profile for careful lookup work.",
                "instructions": "agents/researcher.md",
                "slots": ["research"],
            },
        ],
    }


def test_manifest_parses_workspace_safe_capabilities() -> None:
    manifest = validate_plugin_manifest(_valid_manifest(), source_type="workspace")

    assert manifest.id == "search_pack"
    assert [capability.type for capability in manifest.capabilities] == [
        "cli_tool",
        "settings",
        "skill",
        "agent_profile",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "Bad Id"),
        ("name", "bad name"),
        ("version", " "),
    ],
)
def test_manifest_rejects_invalid_top_level_fields(field: str, value: str) -> None:
    raw = _valid_manifest()
    raw[field] = value

    with pytest.raises(PluginManifestError):
        validate_plugin_manifest(raw, source_type="bundled")


def test_manifest_forbids_unknown_fields() -> None:
    raw = _valid_manifest()
    raw["extra"] = "nope"

    with pytest.raises(PluginManifestError):
        validate_plugin_manifest(raw, source_type="bundled")


def test_manifest_requires_capabilities() -> None:
    raw = _valid_manifest()
    raw["capabilities"] = []

    with pytest.raises(PluginManifestError, match="at least one capability"):
        validate_plugin_manifest(raw, source_type="bundled")


def test_manifest_rejects_duplicate_capability_ids() -> None:
    raw = _valid_manifest()
    capabilities = list(cast(list[dict[str, object]], raw["capabilities"]))
    duplicate = dict(capabilities[0])
    capabilities.append(duplicate)
    raw["capabilities"] = capabilities

    with pytest.raises(PluginManifestError, match="capability ids"):
        validate_plugin_manifest(raw, source_type="bundled")


def test_manifest_rejects_bad_env_key() -> None:
    raw = _valid_manifest()
    raw["env"] = [{"name": "not-valid", "label": "Bad"}]

    with pytest.raises(PluginManifestError, match="uppercase"):
        validate_plugin_manifest(raw, source_type="bundled")


def test_manifest_rejects_undeclared_capability_permissions() -> None:
    raw = _valid_manifest()
    raw["permissions"] = ["secrets"]

    with pytest.raises(PluginManifestError, match="undeclared permissions"):
        validate_plugin_manifest(raw, source_type="bundled")


def test_workspace_manifest_rejects_python_adapters() -> None:
    raw = _valid_manifest()
    raw["permissions"] = []
    raw["capabilities"] = [
        {
            "type": "provider",
            "id": "python_provider",
            "title": "Python Provider",
            "description": "Trusted provider that imports Python runtime code.",
            "entrypoint": "app.providers.example:create_provider",
        }
    ]

    with pytest.raises(PluginManifestError, match="cannot contribute"):
        validate_plugin_manifest(raw, source_type="workspace")


def test_workspace_manifest_rejects_direct_cli_tool_exposure() -> None:
    raw = _valid_manifest()
    capabilities = cast(list[dict[str, object]], raw["capabilities"])
    capabilities[0]["exposure"] = "direct_and_catalog"

    with pytest.raises(PluginManifestError, match="cannot expose CLI tools directly"):
        validate_plugin_manifest(raw, source_type="workspace")


def test_bundled_manifest_allows_provider_adapter() -> None:
    raw = _valid_manifest()
    raw["permissions"] = []
    raw["capabilities"] = [
        {
            "type": "provider",
            "id": "python_provider",
            "title": "Python Provider",
            "description": "Trusted provider that imports Python runtime code.",
            "entrypoint": "app.providers.example:create_provider",
            "models": [
                {
                    "id": "example:vendor/model",
                    "name": "Example Model",
                }
            ],
        }
    ]

    manifest = validate_plugin_manifest(raw, source_type="bundled")

    assert manifest.capabilities[0].type == "provider"


def test_duplicate_capability_ids_across_plugins_are_composite_keys() -> None:
    raw_a = _valid_manifest()
    raw_b = _valid_manifest()
    raw_b["id"] = "other_search"
    manifests = (
        validate_plugin_manifest(raw_a, source_type="bundled"),
        validate_plugin_manifest(raw_b, source_type="bundled"),
    )

    catalog = CapabilityCatalog.from_manifests(manifests)

    assert sorted(
        record.key for record in catalog.capabilities if record.capability_id == "web_search"
    ) == [
        "other_search/web_search",
        "search_pack/web_search",
    ]


def test_capability_search_filters_and_sorts_slot_preferences() -> None:
    raw = _valid_manifest()
    capabilities = list(cast(list[dict[str, object]], raw["capabilities"]))
    second = dict(capabilities[0])
    second["id"] = "web_search_backup"
    second["priority"] = 20
    capabilities.append(second)
    raw["capabilities"] = capabilities
    manifest = validate_plugin_manifest(raw, source_type="bundled")
    catalog = CapabilityCatalog.from_manifests((manifest,))

    results = catalog.search(
        CapabilitySearch(slot="web_search", tag="search"),
        slot_preferences=("search_pack/web_search",),
    )

    assert [record.key for record in results] == [
        "search_pack/web_search",
        "search_pack/web_search_backup",
    ]

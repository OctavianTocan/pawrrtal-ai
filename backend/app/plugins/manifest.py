"""Manifest parsing and validation for capability plugins."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.plugins.contributions import (
    Capability,
    DependencySpec,
    EnvVarSpec,
    Permission,
    ValidationSpec,
    capability_declared_permissions,
    capability_requires_trusted_python,
    validate_identifier,
    validate_non_empty,
)
from app.plugins.errors import PluginManifestError

SCHEMA_VERSION: Literal[1] = 1
PluginSourceType = Literal["bundled", "global", "workspace"]
WORKSPACE_SAFE_TYPES = frozenset({"cli_tool", "settings", "skill", "agent_profile"})


class PluginManifest(BaseModel):
    """Top-level plugin manifest loaded from ``plugin.json``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = SCHEMA_VERSION
    id: str
    name: str
    description: str = Field(min_length=20)
    version: str
    enabled_by_default: bool = False
    overrides: str | None = None
    depends_on: tuple[DependencySpec, ...] = Field(default_factory=tuple)
    permissions: tuple[Permission, ...] = Field(default_factory=tuple)
    env: tuple[EnvVarSpec, ...] = Field(default_factory=tuple)
    capabilities: tuple[Capability, ...]
    validation: ValidationSpec = Field(default_factory=ValidationSpec)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_identifier(value, field_name="plugin.id")

    @field_validator("overrides")
    @classmethod
    def _validate_overrides(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_identifier(value, field_name="plugin.overrides")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        clean = validate_non_empty(value, field_name="plugin name")
        if "_" in clean or clean[0] != clean[0].upper():
            raise ValueError("plugin name must be user-facing Title Case text")
        return clean

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        return validate_non_empty(value, field_name="plugin version")

    @model_validator(mode="after")
    def _validate_manifest_contract(self) -> PluginManifest:
        if not self.capabilities:
            raise ValueError("plugins must declare at least one capability")
        capability_ids = [capability.id for capability in self.capabilities]
        if len(set(capability_ids)) != len(capability_ids):
            raise ValueError("capability ids must be unique within a plugin")
        env_names = [spec.name for spec in self.all_env_specs()]
        if len(set(env_names)) != len(env_names):
            raise ValueError("env var names must be unique within a plugin")
        self._validate_permission_declarations()
        return self

    def all_env_specs(self) -> tuple[EnvVarSpec, ...]:
        """Return top-level and settings-declared env specs."""
        from app.plugins.contributions import SettingsCapability  # noqa: PLC0415

        settings_env: list[EnvVarSpec] = []
        for capability in self.capabilities:
            if isinstance(capability, SettingsCapability):
                settings_env.extend(capability.env)
        return (*self.env, *settings_env)

    def _validate_permission_declarations(self) -> None:
        """Ensure capability permissions are declared at plugin level."""
        declared = set(self.permissions)
        for capability in self.capabilities:
            required = set(capability_declared_permissions(capability))
            missing = required - declared
            if missing:
                raise ValueError(
                    f"capability {capability.id!r} uses undeclared permissions: {sorted(missing)}"
                )


def parse_plugin_manifest(raw: str | bytes | dict[str, Any]) -> PluginManifest:
    """Parse one plugin manifest and normalize validation errors."""
    try:
        if isinstance(raw, bytes):
            return PluginManifest.model_validate_json(raw)
        if isinstance(raw, str):
            return PluginManifest.model_validate_json(raw.encode())
        return PluginManifest.model_validate(raw)
    except ValueError as exc:
        raise PluginManifestError(str(exc)) from exc


def validate_plugin_manifest(
    raw: str | bytes | dict[str, Any],
    *,
    source_type: PluginSourceType,
) -> PluginManifest:
    """Parse and enforce source-specific trust rules for a manifest."""
    manifest = parse_plugin_manifest(raw)
    if source_type == "workspace":
        _reject_untrusted_workspace_manifest(manifest)
    return manifest


def _reject_untrusted_workspace_manifest(manifest: PluginManifest) -> None:
    """Reject workspace plugins that require trusted Python loading."""
    for capability in manifest.capabilities:
        if capability.type not in WORKSPACE_SAFE_TYPES:
            raise PluginManifestError(
                f"Workspace plugin {manifest.id!r} cannot contribute {capability.type!r} yet."
            )
        if capability_requires_trusted_python(capability):
            raise PluginManifestError(
                f"Workspace plugin {manifest.id!r} cannot use Python adapters yet."
            )

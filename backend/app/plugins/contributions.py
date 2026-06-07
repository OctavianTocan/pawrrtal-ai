"""Typed capability models for Pawrrtal plugin manifests."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
CAPABILITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,95}$")
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

Permission = Literal[
    "subprocess",
    "secrets",
    "network",
    "filesystem_read",
    "filesystem_write",
    "external_read",
    "external_write",
    "destructive",
    "costly",
    "publishing",
    "credentialed_mutation",
]
CapabilityExposure = Literal["direct", "catalog", "direct_and_catalog"]
RiskLevel = Literal[
    "local_read",
    "external_read",
    "external_write",
    "destructive",
    "costly",
    "publishing",
    "credentialed_mutation",
]
EnvScope = Literal["workspace", "gateway", "user_workspace"]


def validate_identifier(value: str, *, field_name: str) -> str:
    """Validate a lowercase plan-compatible identifier."""
    if not PLUGIN_ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must match [a-z][a-z0-9_]{{1,62}} and stay lowercase")
    return value


def validate_capability_id(value: str, *, field_name: str) -> str:
    """Validate a lowercase capability identifier."""
    if not CAPABILITY_ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must match [a-z][a-z0-9_]{{1,95}} and stay lowercase")
    return value


def validate_non_empty(value: str, *, field_name: str) -> str:
    """Validate a user-visible non-empty string."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped


class FrozenModel(BaseModel):
    """Base model for strict immutable manifest objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EnvVarSpec(FrozenModel):
    """One env key declared by a plugin manifest."""

    name: str
    inject_as: str | None = None
    required: bool = True
    scope: EnvScope = "workspace"
    overridable: bool = True
    gateway_fallback: bool = False
    secret: bool = True
    label: str
    description: str | None = None
    help_url: str | None = None

    @field_validator("name", "inject_as")
    @classmethod
    def _validate_env_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not ENV_KEY_RE.fullmatch(value):
            raise ValueError("env var names must be uppercase snake case")
        return value

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        return validate_non_empty(value, field_name="env label")


class ValidationCommand(FrozenModel):
    """One command used to validate a plugin after install or change."""

    name: str
    entrypoint: tuple[str, ...]
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    inject_env: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_non_empty(value, field_name="validation command name")

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("validation entrypoint must not be empty")
        return tuple(validate_non_empty(part, field_name="entrypoint part") for part in value)


class ValidationSpec(FrozenModel):
    """Validation commands declared by a plugin."""

    commands: tuple[ValidationCommand, ...] = Field(default_factory=tuple)


class DependencySpec(FrozenModel):
    """A dependency on another plugin."""

    id: str
    min_schema_version: int = 1

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_identifier(value, field_name="dependency.id")


class CapabilityBase(FrozenModel):
    """Common searchable metadata on every capability."""

    id: str
    title: str | None = None
    description: str = Field(min_length=20)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    intents: tuple[str, ...] = Field(default_factory=tuple)
    slots: tuple[str, ...] = Field(default_factory=tuple)
    priority: int = 0
    exposure: CapabilityExposure = "catalog"
    permissions: tuple[Permission, ...] = Field(default_factory=tuple)
    risk: RiskLevel = "local_read"
    requires_confirmation: bool = False
    output_schema: dict[str, Any] = Field(default_factory=dict)
    examples: tuple[dict[str, Any], ...] = Field(default_factory=tuple)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_capability_id(value, field_name="capability.id")

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_non_empty(value, field_name="capability title")

    @field_validator("tags", "intents", "slots")
    @classmethod
    def _validate_terms(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        clean = tuple(validate_non_empty(v, field_name="capability term") for v in values)
        if len(set(clean)) != len(clean):
            raise ValueError("capability term lists must not contain duplicates")
        return clean


class CliToolCapability(CapabilityBase):
    """A CLI-backed tool capability."""

    type: Literal["cli_tool"] = "cli_tool"
    tool_name: str
    entrypoint: tuple[str, ...]
    cwd: Literal["plugin", "workspace"] = "plugin"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    output_cap_bytes: int = Field(default=32_000, ge=1, le=1_000_000)
    args_schema: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        return validate_capability_id(value, field_name="tool_name")

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("cli_tool entrypoint must not be empty")
        return tuple(validate_non_empty(part, field_name="entrypoint part") for part in value)


class PythonToolCapability(CapabilityBase):
    """A trusted Python-backed tool capability."""

    type: Literal["python_tool"] = "python_tool"
    tool_name: str
    entrypoint: str
    exposure: CapabilityExposure = "direct"

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        return validate_capability_id(value, field_name="tool_name")


class TurnContextProviderCapability(CapabilityBase):
    """A pre-turn context provider capability."""

    type: Literal["turn_context_provider"] = "turn_context_provider"
    entrypoint: str
    order: int = 100
    budget: dict[str, Any] = Field(default_factory=dict)


class TurnObserverCapability(CapabilityBase):
    """A turn lifecycle observer capability."""

    type: Literal["turn_observer"] = "turn_observer"
    entrypoint: str
    order: int = 100


class ProviderModel(FrozenModel):
    """One model declared by a provider plugin."""

    id: str
    name: str
    sort_order: int = 0
    default: bool = False
    reasoning: tuple[str, ...] = Field(default_factory=tuple)
    supports_images: bool = False
    supports_tools: bool = True


class ProviderCapability(CapabilityBase):
    """A model provider capability."""

    type: Literal["provider"] = "provider"
    entrypoint: str
    auth: dict[str, Any] = Field(default_factory=dict)
    models: tuple[ProviderModel, ...] = Field(default_factory=tuple)
    lifecycle: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeCapability(CapabilityBase):
    """An agent-runtime adapter capability."""

    type: Literal["agent_runtime"] = "agent_runtime"
    entrypoint: str
    sessions: dict[str, Any] = Field(default_factory=dict)
    events: tuple[str, ...] = Field(default_factory=tuple)
    tool_schema_adapter: str | None = None


class AgentProfileCapability(CapabilityBase):
    """A searchable agent profile; execution remains kernel-owned."""

    type: Literal["agent_profile"] = "agent_profile"
    instructions: str
    tools: tuple[str, ...] = Field(default_factory=tuple)
    runtime_preferences: tuple[str, ...] = Field(default_factory=tuple)
    model_preferences: tuple[str, ...] = Field(default_factory=tuple)
    memory: dict[str, Any] = Field(default_factory=dict)


class ChannelCapability(CapabilityBase):
    """A channel ingress/delivery capability."""

    type: Literal["channel"] = "channel"
    surface: str
    entrypoint: str
    commands: dict[str, Any] = Field(default_factory=dict)
    lifespan: dict[str, Any] = Field(default_factory=dict)


class RouterCapability(CapabilityBase):
    """A bundled plugin API router capability."""

    type: Literal["router"] = "router"
    entrypoint: str
    prefix: str
    tags: tuple[str, ...] = Field(default_factory=tuple)


class SettingsCapability(CapabilityBase):
    """Plugin settings metadata."""

    type: Literal["settings"] = "settings"
    env: tuple[EnvVarSpec, ...] = Field(default_factory=tuple)


class SkillCapability(CapabilityBase):
    """A skill file exposed by a plugin bundle."""

    type: Literal["skill"] = "skill"
    path: str


class MigrationProviderCapability(CapabilityBase):
    """A migration/import provider capability."""

    type: Literal["migration_provider"] = "migration_provider"
    provider: str
    entrypoint: str


class SchedulerCapability(CapabilityBase):
    """A scheduler/lifecycle capability."""

    type: Literal["scheduler"] = "scheduler"
    entrypoint: str


Capability = Annotated[
    CliToolCapability
    | PythonToolCapability
    | TurnContextProviderCapability
    | TurnObserverCapability
    | ProviderCapability
    | AgentRuntimeCapability
    | AgentProfileCapability
    | ChannelCapability
    | RouterCapability
    | SettingsCapability
    | SkillCapability
    | MigrationProviderCapability
    | SchedulerCapability,
    Field(discriminator="type"),
]


def capability_requires_trusted_python(capability: Capability) -> bool:
    """Return whether a capability requires trusted Python code loading."""
    return not isinstance(
        capability,
        CliToolCapability | SettingsCapability | SkillCapability | AgentProfileCapability,
    )


def capability_declared_permissions(capability: Capability) -> tuple[Permission, ...]:
    """Return explicit plus implied permissions for one capability."""
    implied: list[Permission] = []
    if isinstance(capability, CliToolCapability):
        implied.append("subprocess")
    return tuple(dict.fromkeys((*capability.permissions, *implied)))

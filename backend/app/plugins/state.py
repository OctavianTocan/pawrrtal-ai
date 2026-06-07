"""Persistent enablement and preference state for plugins."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.plugins.errors import PluginStateError
from app.plugins.manifest import PluginSourceType

StateScope = Literal["global", "workspace"]


class CapabilityState(BaseModel):
    """Enablement state for one capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True


class ValidationCheck(BaseModel):
    """One validation or doctor check result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: str
    message: str


class ValidationResult(BaseModel):
    """Last validation command result saved in plugin state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    checks: tuple[ValidationCheck, ...] = Field(default_factory=tuple)


class DoctorState(BaseModel):
    """Last lightweight doctor status saved in plugin state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    checked_at: datetime


class PluginState(BaseModel):
    """State persisted per plugin id and workspace/global scope."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    enabled: bool
    capabilities: Mapping[str, CapabilityState] = Field(default_factory=dict)
    slot_preferences: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    validated_fingerprint: str | None = None
    validated_at: datetime | None = None
    last_validation: ValidationResult | None = None
    failure_reason: str | None = None
    doctor: DoctorState | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("slot_preferences", mode="before")
    @classmethod
    def _coerce_slot_preferences(cls, value: object) -> object:
        if isinstance(value, dict):
            return {str(k): tuple(v) for k, v in value.items()}
        return value

    @model_validator(mode="after")
    def _freeze_nested_maps(self) -> PluginState:
        object.__setattr__(self, "capabilities", MappingProxyType(dict(self.capabilities)))
        object.__setattr__(
            self,
            "slot_preferences",
            MappingProxyType({k: tuple(v) for k, v in self.slot_preferences.items()}),
        )
        return self

    def is_capability_enabled(self, capability_id: str) -> bool:
        """Return whether a capability is enabled under this state."""
        state = self.capabilities.get(capability_id)
        return self.enabled and (state is None or state.enabled)

    def slot_preference_keys(self, slot_id: str) -> tuple[str, ...]:
        """Return ordered composite capability keys preferred for a slot."""
        return self.slot_preferences.get(slot_id, ())

    def to_json_payload(self) -> dict[str, object]:
        """Return a plan-shaped JSON payload for persistence."""
        return {
            "enabled": self.enabled,
            "capabilities": {
                key: value.model_dump(mode="json") for key, value in self.capabilities.items()
            },
            "slot_preferences": {
                key: list(values) for key, values in self.slot_preferences.items()
            },
            "validated_fingerprint": self.validated_fingerprint,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "last_validation": (
                self.last_validation.model_dump(mode="json") if self.last_validation else None
            ),
            "failure_reason": self.failure_reason,
            "doctor": self.doctor.model_dump(mode="json") if self.doctor else None,
            "updated_at": self.updated_at.isoformat(),
        }


def default_state(*, enabled_by_default: bool, source_type: PluginSourceType) -> PluginState:
    """Return default enablement state for a missing state file."""
    return PluginState(enabled=source_type == "bundled" and enabled_by_default)


def plugin_state_path(
    *,
    plugin_id: str,
    scope: StateScope,
    pawrrtal_home: Path | None = None,
    workspace_root: Path | None = None,
) -> Path:
    """Return the persisted state path for one plugin."""
    if scope == "workspace":
        if workspace_root is None:
            raise PluginStateError("workspace_root is required for workspace plugin state")
        return workspace_root / ".agent" / "plugin-state" / f"{plugin_id}.json"
    if pawrrtal_home is None:
        pawrrtal_home = Path(os.environ.get("PAWRRTAL_HOME", Path.home() / ".pawrrtal"))
    return pawrrtal_home / "plugin-state" / f"{plugin_id}.json"


def load_plugin_state(
    path: Path,
    *,
    enabled_by_default: bool,
    source_type: PluginSourceType,
) -> PluginState:
    """Load state from disk or return the manifest default."""
    if not path.exists():
        return default_state(enabled_by_default=enabled_by_default, source_type=source_type)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PluginState.model_validate(raw)
    except (OSError, ValueError) as exc:
        raise PluginStateError(f"Invalid plugin state at {path}: {exc}") from exc


def save_plugin_state(path: Path, state: PluginState) -> None:
    """Atomically persist one plugin state file with an advisory lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with _locked(lock_path):
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = state.to_json_payload()
        with tmp.open("w", encoding="utf-8") as tmp_file:
            json.dump(payload, tmp_file, sort_keys=True, indent=2)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp.replace(path)
        _fsync_dir(path.parent)


@contextmanager
def _locked(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock for one state write."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _fsync_dir(path: Path) -> None:
    """Fsync a directory after an atomic rename."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

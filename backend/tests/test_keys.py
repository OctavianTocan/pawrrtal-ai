"""Unit tests for app.core.keys.

Covers:
  * Round-trip save/load — values come back out unchanged.
  * Empty-string strip on save — clearing a field reverts to the gateway
    default rather than persisting an empty override.
  * resolve_api_key precedence — workspace override wins over settings.
  * resolve_api_key fallback — settings is returned when no override exists.
  * resolve_api_key with unknown key — returns None.
  * Corrupt/invalid-token recovery — quarantines the file and returns ``{}``.
  * Newline rejection regex catches both LF and CR.
  * Hardcoded path bug regression — ``settings.workspace_base_dir`` is honoured.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.core import keys
from app.core.config import settings


@pytest.fixture
def tmp_workspace_base(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point WORKSPACE_BASE at a writable tmp dir for the duration of one test.

    Patches the live `settings` instance because `_workspace_env_path`
    re-reads `settings.workspace_base_dir` on every call (so test
    monkey-patches take effect immediately).
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    return tmp_path


def test_save_and_load_round_trips(tmp_workspace_base: Path) -> None:
    """Saving then loading returns the same key/value pairs."""
    workspace_id = uuid4()
    keys.save_workspace_env(workspace_id, {"GEMINI_API_KEY": "real-gemini-key"})
    loaded = keys.load_workspace_env(workspace_id)
    assert loaded == {"GEMINI_API_KEY": "real-gemini-key"}


def test_save_strips_empty_values(tmp_workspace_base: Path) -> None:
    """Empty-string values are NOT persisted (clear-and-save reverts to default).

    The frontend sends `""` when a user clears an input. Persisting that
    as `KEY=` would be ambiguous on read; the resolver also treats empty
    string as "no override". Strip during save keeps the on-disk file
    consistent with what the resolver actually honours.
    """
    workspace_id = uuid4()
    keys.save_workspace_env(
        workspace_id,
        {"GEMINI_API_KEY": "kept", "EXA_API_KEY": ""},
    )
    loaded = keys.load_workspace_env(workspace_id)
    assert loaded == {"GEMINI_API_KEY": "kept"}
    assert "EXA_API_KEY" not in loaded


def test_load_returns_empty_when_no_file(tmp_workspace_base: Path) -> None:
    """A user who never saved a workspace .env loads as ``{}``."""
    assert keys.load_workspace_env(uuid4()) == {}


def test_resolve_api_key_prefers_workspace_override(
    tmp_workspace_base: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both workspace override and settings are set, override wins."""
    monkeypatch.setattr(settings, "exa_api_key", "from-settings")
    workspace_id = uuid4()
    keys.save_workspace_env(workspace_id, {"EXA_API_KEY": "from-workspace"})
    assert keys.resolve_api_key(workspace_id, "EXA_API_KEY") == "from-workspace"


def test_resolve_api_key_falls_back_to_settings(
    tmp_workspace_base: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No override → returns the corresponding `settings` field value.

    This is the load-bearing contract that lets call sites stop writing
    `resolve_api_key(...) or settings.x` (the dead-code pattern fixed in
    Bean A across stt.py / agent_tools.py / agents.py).
    """
    monkeypatch.setattr(settings, "exa_api_key", "from-settings")
    workspace_id = uuid4()
    assert keys.resolve_api_key(workspace_id, "EXA_API_KEY") == "from-settings"


def test_resolve_api_key_returns_none_for_unset(
    tmp_workspace_base: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No override and empty settings → returns None (not empty string)."""
    monkeypatch.setattr(settings, "exa_api_key", "")
    assert keys.resolve_api_key(uuid4(), "EXA_API_KEY") is None


def test_resolve_api_key_unknown_key_returns_none(tmp_workspace_base: Path) -> None:
    """A key not in `_SETTINGS_ATTR_MAP` returns None without raising.

    The HTTP layer rejects unknown keys with 400 before they reach
    `resolve_api_key`, but defensive callers should still get a clean
    None rather than a `getattr` crash.
    """
    assert keys.resolve_api_key(uuid4(), "NOT_A_REAL_KEY") is None


def test_load_quarantines_corrupt_file(tmp_workspace_base: Path) -> None:
    """A file that doesn't decrypt is renamed aside and an empty dict returned.

    Without this, a key rotation or partial write would 500 every
    request for that user permanently.
    """
    workspace_id = uuid4()
    path = keys._workspace_env_path(workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not encrypted at all")

    loaded = keys.load_workspace_env(workspace_id)

    assert loaded == {}
    assert not path.exists(), "corrupt file should have been renamed aside"
    siblings = list(path.parent.iterdir())
    assert any(s.name.startswith(".env.corrupt-") for s in siblings)


def test_value_forbidden_chars_matches_lf_and_cr() -> None:
    """The newline-rejection regex blocks both LF and CR injection vectors."""
    assert keys.VALUE_FORBIDDEN_CHARS.search("foo\nbar")
    assert keys.VALUE_FORBIDDEN_CHARS.search("foo\rbar")
    assert keys.VALUE_FORBIDDEN_CHARS.search("foo\r\nbar")
    assert keys.VALUE_FORBIDDEN_CHARS.search("\nleading-newline") is not None
    assert keys.VALUE_FORBIDDEN_CHARS.search("clean-key") is None


def test_workspace_path_uses_settings_workspace_base_dir(
    tmp_workspace_base: Path,
) -> None:
    """The encrypted .env lands under settings.workspace_base_dir.

    Regression test for the original PR's blocking bug: keys.py used
    a hardcoded `Path("/workspace")` that ignored the configured base
    dir, causing data loss on Docker (volume mounts `/data/workspaces`)
    and PermissionError on macOS dev (no `/workspace` directory).
    """
    workspace_id = uuid4()
    keys.save_workspace_env(workspace_id, {"GEMINI_API_KEY": "val"})
    expected = tmp_workspace_base / str(workspace_id) / ".env"
    assert expected.exists()
    assert expected.parent.parent == tmp_workspace_base

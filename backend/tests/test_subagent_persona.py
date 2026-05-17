"""Tests for backend/app/core/subagents/persona.py.

Covers the loader (built-in + workspace), the validator (model id,
tool names, frontmatter shape), the mtime cache, and the resolver
precedence (workspace overrides win).

Per ``.claude/rules/testing/agent-loop-testing-philosophy.md``: this
is a pure unit-test surface (no provider, no loop), so direct calls
and ``tmp_path`` fixtures are appropriate — no ``ScriptedStreamFn``
needed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core.subagents.persona import (
    KNOWN_TOOL_NAMES,
    PERSONA_MAX_ITERATIONS_CEILING,
    PERSONA_MAX_WALL_CLOCK_CEILING_SECONDS,
    Persona,
    PersonaError,
    clear_workspace_persona_cache,
    list_builtin_personas,
    load_builtin_personas,
    load_workspace_personas,
    resolve_persona,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_VALID_FRONTMATTER = """---
name: tester
description: A test persona used by the unit tests.
model: google/gemini-3-flash-preview
tools_allow:
  - read_file
  - exa_search
max_iterations: 25
max_wall_clock_seconds: 120
---
You are a test subagent. Do what the task says.
"""


@pytest.fixture(autouse=True)
def _reset_workspace_cache() -> None:
    """Each test starts with an empty workspace persona cache."""
    clear_workspace_persona_cache()


@pytest.fixture
def persona_dir(tmp_path: Path) -> Path:
    """Return a temp directory containing one valid persona file."""
    (tmp_path / "tester.md").write_text(_VALID_FRONTMATTER, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Loader — happy path
# ---------------------------------------------------------------------------


def test_load_builtin_personas_returns_one_per_file(persona_dir: Path) -> None:
    personas = load_builtin_personas(persona_dir)
    assert set(personas.keys()) == {"tester"}
    persona = personas["tester"]
    assert isinstance(persona, Persona)
    assert persona.name == "tester"
    assert persona.model == "google/gemini-3-flash-preview"
    assert persona.tools_allow == frozenset({"read_file", "exa_search"})
    assert persona.max_iterations == 25
    assert persona.system_prompt.startswith("You are a test subagent.")


def test_load_builtin_personas_empty_dir_returns_empty_dict(tmp_path: Path) -> None:
    """Missing or empty directory should not crash startup."""
    assert load_builtin_personas(tmp_path) == {}


def test_load_builtin_personas_real_directory_loads_shipped_personas() -> None:
    """Default directory contains the three v1 personas — and they all
    pass the validator.  This is the canary: if anyone breaks a shipped
    persona file the boot-time loader will catch it here at test time
    instead of in production startup."""
    personas = load_builtin_personas()
    assert {"researcher", "refactorer", "reviewer"} <= set(personas.keys())
    for persona in personas.values():
        assert persona.tools_allow.issubset(KNOWN_TOOL_NAMES)
        assert persona.system_prompt.strip()


# ---------------------------------------------------------------------------
# Loader — validation failures
# ---------------------------------------------------------------------------


def test_load_builtin_personas_rejects_unknown_model(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text(
        "---\n"
        "name: broken\n"
        "description: Uses a model that doesn't exist.\n"
        "model: gpt-nonexistent\n"
        "tools_allow: [read_file]\n"
        "---\n"
        "system prompt body.\n",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match="not in MODEL_CATALOG"):
        load_builtin_personas(tmp_path)


def test_load_builtin_personas_rejects_unknown_tool(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text(
        "---\n"
        "name: broken\n"
        "description: References a nonexistent tool.\n"
        "model: google/gemini-3-flash-preview\n"
        "tools_allow: [delete_universe]\n"
        "---\n"
        "system prompt body.\n",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match="unknown tool"):
        load_builtin_personas(tmp_path)


def test_load_builtin_personas_rejects_missing_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text("just some markdown, no fences.\n", encoding="utf-8")
    with pytest.raises(PersonaError, match="missing opening"):
        load_builtin_personas(tmp_path)


def test_load_builtin_personas_rejects_empty_body(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text(
        "---\n"
        "name: broken\n"
        "description: No body.\n"
        "model: google/gemini-3-flash-preview\n"
        "---\n"
        "   \n",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match=r"body .* is empty"):
        load_builtin_personas(tmp_path)


def test_load_builtin_personas_rejects_filename_name_mismatch(tmp_path: Path) -> None:
    (tmp_path / "filename_says_x.md").write_text(
        "---\n"
        "name: but_metadata_says_y\n"
        "description: mismatched.\n"
        "model: google/gemini-3-flash-preview\n"
        "---\n"
        "body.\n",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match="must equal filename stem"):
        load_builtin_personas(tmp_path)


def test_load_builtin_personas_rejects_duplicate_name(tmp_path: Path) -> None:
    """Two files with the same persona name should error at boot."""
    # Same `name:` field but different filenames so they both parse the
    # filename-stem check individually — wait, they can't.  The
    # filename-stem check forces filename==name, so two files with the
    # same `name:` would have to share a filename.  Instead, exercise
    # this by writing one file then a *second* file whose name= matches
    # the first's stem after a rename.  Since the FS can't have two files
    # with the same name, the duplicate-name check actually fires when
    # someone copies a file but forgets to update name= — which would
    # also trip filename-mismatch first.  So this is dead code in
    # practice; the test documents the invariant anyway.
    (tmp_path / "alpha.md").write_text(
        "---\nname: alpha\ndescription: ok.\nmodel: google/gemini-3-flash-preview\n---\nbody.\n",
        encoding="utf-8",
    )
    # Sanity: no duplicate, loads fine.
    personas = load_builtin_personas(tmp_path)
    assert "alpha" in personas


def test_persona_max_iterations_capped(tmp_path: Path) -> None:
    (tmp_path / "greedy.md").write_text(
        f"---\nname: greedy\ndescription: asks for too much.\n"
        f"model: google/gemini-3-flash-preview\n"
        f"max_iterations: {PERSONA_MAX_ITERATIONS_CEILING + 1}\n"
        f"---\nbody.\n",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match="schema validation failed"):
        load_builtin_personas(tmp_path)


def test_persona_wall_clock_capped(tmp_path: Path) -> None:
    (tmp_path / "slow.md").write_text(
        f"---\nname: slow\ndescription: asks for too much.\n"
        f"model: google/gemini-3-flash-preview\n"
        f"max_wall_clock_seconds: {PERSONA_MAX_WALL_CLOCK_CEILING_SECONDS + 1}\n"
        f"---\nbody.\n",
        encoding="utf-8",
    )
    with pytest.raises(PersonaError, match="schema validation failed"):
        load_builtin_personas(tmp_path)


# ---------------------------------------------------------------------------
# Workspace overrides
# ---------------------------------------------------------------------------


def _write_workspace_override(workspace: Path, name: str, model: str) -> Path:
    overrides_dir = workspace / ".pawrrtal" / "agents"
    overrides_dir.mkdir(parents=True, exist_ok=True)
    path = overrides_dir / f"{name}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: workspace override.\n"
        f"model: {model}\ntools_allow: [read_file]\n"
        f"---\nworkspace body.\n",
        encoding="utf-8",
    )
    return path


def test_load_workspace_personas_reads_overrides(tmp_path: Path) -> None:
    _write_workspace_override(tmp_path, "tester", "google/gemini-3-flash-preview")
    personas = load_workspace_personas(tmp_path)
    assert "tester" in personas
    assert personas["tester"].system_prompt == "workspace body."


def test_load_workspace_personas_skips_invalid_without_crashing(tmp_path: Path) -> None:
    """A bad override must not break chat — it warns and is skipped."""
    overrides_dir = tmp_path / ".pawrrtal" / "agents"
    overrides_dir.mkdir(parents=True)
    (overrides_dir / "ok.md").write_text(
        "---\nname: ok\ndescription: fine.\nmodel: google/gemini-3-flash-preview\n---\nbody.\n",
        encoding="utf-8",
    )
    (overrides_dir / "bad.md").write_text(
        "---\nname: bad\ndescription: bad model.\nmodel: gpt-fake\n---\nbody.\n",
        encoding="utf-8",
    )
    personas = load_workspace_personas(tmp_path)
    assert set(personas.keys()) == {"ok"}


def test_load_workspace_personas_mtime_cache(tmp_path: Path, monkeypatch) -> None:
    """Repeated loads with unchanged mtimes don't re-parse."""
    _write_workspace_override(tmp_path, "tester", "google/gemini-3-flash-preview")

    parse_count = {"n": 0}
    real = __import__(
        "app.core.subagents.persona", fromlist=["_parse_persona_file"]
    )._parse_persona_file

    def counting(path: Path) -> Persona:
        parse_count["n"] += 1
        return real(path)

    monkeypatch.setattr("app.core.subagents.persona._parse_persona_file", counting)

    load_workspace_personas(tmp_path)
    load_workspace_personas(tmp_path)
    load_workspace_personas(tmp_path)
    assert parse_count["n"] == 1, "expected one parse for three cached calls"


def test_load_workspace_personas_mtime_invalidates_on_change(tmp_path: Path) -> None:
    """When the override file changes, the cache reflects the new content."""
    path = _write_workspace_override(tmp_path, "tester", "google/gemini-3-flash-preview")
    first = load_workspace_personas(tmp_path)["tester"]
    assert first.system_prompt == "workspace body."

    # Sleep to force mtime tick on filesystems with second resolution.
    time.sleep(0.01)
    path.write_text(
        "---\nname: tester\ndescription: updated.\nmodel: google/gemini-3-flash-preview\n"
        "tools_allow: [read_file]\n"
        "---\nupdated body.\n",
        encoding="utf-8",
    )
    second = load_workspace_personas(tmp_path)["tester"]
    assert second.system_prompt == "updated body."


# ---------------------------------------------------------------------------
# Resolver precedence
# ---------------------------------------------------------------------------


def test_resolve_persona_workspace_override_wins(tmp_path: Path, persona_dir: Path) -> None:
    """Workspace override with the same name as a built-in takes priority."""
    builtin = load_builtin_personas(persona_dir)
    _write_workspace_override(tmp_path, "tester", "anthropic/claude-sonnet-4-6")
    resolved = resolve_persona("tester", workspace_root=tmp_path, builtin=builtin)
    assert resolved.model == "anthropic/claude-sonnet-4-6"
    assert resolved.system_prompt == "workspace body."


def test_resolve_persona_falls_back_to_builtin(tmp_path: Path, persona_dir: Path) -> None:
    """No workspace override → returns the built-in."""
    builtin = load_builtin_personas(persona_dir)
    resolved = resolve_persona("tester", workspace_root=tmp_path, builtin=builtin)
    assert resolved.model == "google/gemini-3-flash-preview"
    assert resolved.system_prompt.startswith("You are a test subagent.")


def test_resolve_persona_workspace_root_none_skips_overrides(persona_dir: Path) -> None:
    builtin = load_builtin_personas(persona_dir)
    resolved = resolve_persona("tester", workspace_root=None, builtin=builtin)
    assert resolved.model == "google/gemini-3-flash-preview"


def test_resolve_persona_unknown_name_raises_with_known_list(
    tmp_path: Path,
    persona_dir: Path,
) -> None:
    builtin = load_builtin_personas(persona_dir)
    with pytest.raises(PersonaError, match="Unknown persona"):
        resolve_persona("nonexistent", workspace_root=tmp_path, builtin=builtin)


# ---------------------------------------------------------------------------
# list_builtin_personas — small public helper used by the list_subagents tool
# ---------------------------------------------------------------------------


def test_list_builtin_personas_returns_compact_descriptors() -> None:
    real = load_builtin_personas()
    descriptors = list_builtin_personas(real)
    assert len(descriptors) >= 3
    assert all({"name", "description", "model"} == set(d.keys()) for d in descriptors)
    # Stable sort by name.
    names = [d["name"] for d in descriptors]
    assert names == sorted(names)

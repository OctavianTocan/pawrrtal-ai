"""Tests for the Gemini CLI provider's pure helpers.

The provider drives a subprocess (``gemini --acp``) so end-to-end
tests require the binary on PATH. These tests focus on the
deterministic pieces:

* :func:`is_gemini_cli_available` honours ``shutil.which``.
* :func:`render_history_prefix` flattens history + system prompt.
* :func:`PawrrtalAcpClient.text_from_content_block` extracts text.
* :func:`PawrrtalAcpClient.pick_allow_option` prefers ``allow_once``.
* :func:`_ensure_workspace_path` rejects paths outside the workspace.
* The catalog includes the five Gemini CLI models.
* The factory dispatches ``Host.gemini_cli`` to :class:`GeminiCliLLM`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.providers.catalog import MODEL_CATALOG
from app.core.providers.factory import resolve_llm
from app.core.providers.gemini_cli_provider import (
    GeminiCliLLM,
    is_gemini_cli_available,
    render_history_prefix,
)
from app.core.providers.model_id import Host, Vendor

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


GEMINI_CLI_MODELS = (
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview",
)


def test_catalog_lists_all_five_gemini_cli_models() -> None:
    cli_entries = [e for e in MODEL_CATALOG if e.host is Host.gemini_cli]
    assert {e.model for e in cli_entries} == set(GEMINI_CLI_MODELS)
    for entry in cli_entries:
        assert entry.vendor is Vendor.google
        # CLI uses local Google account auth — not API-billed via us.
        assert entry.cost_per_mtok_in_usd == 0.0
        assert entry.cost_per_mtok_out_usd == 0.0


def test_catalog_ids_use_gemini_cli_host_prefix() -> None:
    cli_entries = [e for e in MODEL_CATALOG if e.host is Host.gemini_cli]
    for entry in cli_entries:
        assert entry.id == f"gemini-cli:google/{entry.model}"


# ---------------------------------------------------------------------------
# Factory dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", GEMINI_CLI_MODELS)
def test_factory_routes_gemini_cli_host_to_gemini_cli_llm(model: str) -> None:
    provider = resolve_llm(f"gemini-cli:google/{model}")
    assert isinstance(provider, GeminiCliLLM)


def test_factory_keeps_google_ai_host_on_native_provider() -> None:
    # Sanity check — adding gemini-cli must not steal the canonical
    # google-ai routing from the native SDK provider.
    from app.core.providers.gemini_provider import GeminiLLM

    native = resolve_llm("google-ai:google/gemini-3-flash-preview")
    assert isinstance(native, GeminiLLM)
    assert not isinstance(native, GeminiCliLLM)


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def test_is_gemini_cli_available_when_binary_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.providers.gemini_cli_provider.shutil.which",
        lambda _name: "/usr/local/bin/gemini",
    )
    assert is_gemini_cli_available() is True


def test_is_gemini_cli_available_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.providers.gemini_cli_provider.shutil.which",
        lambda _name: None,
    )
    assert is_gemini_cli_available() is False


# ---------------------------------------------------------------------------
# History prefix rendering
# ---------------------------------------------------------------------------


def test_render_history_prefix_empty_when_no_history_and_no_system_prompt() -> None:
    assert render_history_prefix(history=None, system_prompt=None) == ""
    assert render_history_prefix(history=[], system_prompt="") == ""


def test_render_history_prefix_wraps_system_prompt() -> None:
    out = render_history_prefix(history=None, system_prompt="you are helpful")
    assert "--- BEGIN SYSTEM CONTEXT ---" in out
    assert "you are helpful" in out
    assert "--- END SYSTEM CONTEXT ---" in out


def test_render_history_prefix_wraps_conversation_history() -> None:
    history = [
        {"role": "user", "content": "what's 2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    out = render_history_prefix(history=history, system_prompt=None)
    assert "--- BEGIN PRIOR CONVERSATION ---" in out
    assert "User: what's 2+2?" in out
    assert "Assistant: 4" in out
    assert "--- END PRIOR CONVERSATION ---" in out


def test_render_history_prefix_skips_blank_rows() -> None:
    history = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "   "},
        {"role": "user", "content": "real question"},
    ]
    out = render_history_prefix(history=history, system_prompt=None)
    assert "User: real question" in out
    assert out.count("User:") == 1
    assert "Assistant:" not in out


def test_render_history_prefix_truncates_oversized_bodies() -> None:
    huge_message = "x" * 50_000
    history = [{"role": "user", "content": huge_message}]
    out = render_history_prefix(history=history, system_prompt=None)
    # The hard cap keeps the output under the per-turn budget.
    assert len(out) < 50_000


# ---------------------------------------------------------------------------
# ACP Client subclass helpers
# ---------------------------------------------------------------------------


def test_pick_allow_option_prefers_allow_once() -> None:
    from acp.schema import PermissionOption

    from app.core.providers._gemini_cli_client import pick_allow_option

    options = [
        PermissionOption(option_id="0", name="Always", kind="allow_always"),
        PermissionOption(option_id="1", name="Once", kind="allow_once"),
        PermissionOption(option_id="2", name="No", kind="reject_once"),
    ]
    chosen = pick_allow_option(options)
    assert chosen is not None
    assert chosen.kind == "allow_once"


def test_pick_allow_option_returns_none_when_no_allow_kind() -> None:
    from acp.schema import PermissionOption

    from app.core.providers._gemini_cli_client import pick_allow_option

    options = [
        PermissionOption(option_id="0", name="No", kind="reject_once"),
        PermissionOption(option_id="1", name="Never", kind="reject_always"),
    ]
    assert pick_allow_option(options) is None


def test_text_from_content_block_pulls_text_payload() -> None:
    from acp.schema import TextContentBlock

    from app.core.providers._gemini_cli_client import text_from_content_block

    block = TextContentBlock(type="text", text="hello world")
    assert text_from_content_block(block) == "hello world"


def test_text_from_content_block_returns_empty_for_image_blocks() -> None:
    from acp.schema import ImageContentBlock

    from app.core.providers._gemini_cli_client import text_from_content_block

    block = ImageContentBlock(type="image", data="<base64>", mime_type="image/png")
    assert text_from_content_block(block) == ""


# ---------------------------------------------------------------------------
# Workspace path validation
# ---------------------------------------------------------------------------


def test_ensure_workspace_path_accepts_inside_workspace(tmp_path: Path) -> None:
    from app.core.providers._gemini_cli_client import _ensure_workspace_path

    target = tmp_path / "subdir" / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hi")
    resolved = _ensure_workspace_path(str(target), tmp_path)
    assert resolved == target.resolve()


def test_ensure_workspace_path_rejects_outside_workspace(tmp_path: Path) -> None:
    from acp import RequestError

    from app.core.providers._gemini_cli_client import _ensure_workspace_path

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sibling = tmp_path / "outside" / "secret.txt"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("don't read me")
    with pytest.raises(RequestError):
        _ensure_workspace_path(str(sibling), workspace)


def test_ensure_workspace_path_rejects_relative_path(tmp_path: Path) -> None:
    from acp import RequestError

    from app.core.providers._gemini_cli_client import _ensure_workspace_path

    with pytest.raises(RequestError):
        _ensure_workspace_path("./relative.txt", tmp_path)


def test_ensure_workspace_path_rejects_when_workspace_root_missing(tmp_path: Path) -> None:
    from acp import RequestError

    from app.core.providers._gemini_cli_client import _ensure_workspace_path

    with pytest.raises(RequestError):
        _ensure_workspace_path(str(tmp_path / "file.txt"), None)

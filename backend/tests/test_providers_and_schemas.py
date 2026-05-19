"""Tests for provider routing, workspace-env key resolution, and schema behavior.

This module covers:
- :func:`resolve_llm` routing (model-id prefix → provider class)
- :func:`resolve_llm` workspace_id propagation to providers (workspace env support)
- Schema validation for :class:`ConversationCreate`, :class:`ConversationUpdate`,
  :class:`UserCreate`
- :func:`resolve_api_key` precedence (workspace override > settings fallback)
"""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core import keys
from app.core.config import settings
from app.core.providers.claude_provider import ClaudeLLM
from app.core.providers.factory import resolve_llm
from app.core.providers.gemini_provider import GeminiLLM
from app.core.providers.litellm_provider import LiteLLMLLM
from app.core.providers.model_id import InvalidModelId, Vendor
from app.schemas import ConversationCreate, ConversationUpdate, UserCreate


def test_resolve_llm_accepts_canonical_anthropic_id() -> None:
    """A fully-qualified ``host:vendor/model`` ID routes by host."""
    provider = resolve_llm("agent-sdk:anthropic/claude-sonnet-4-6")
    assert isinstance(provider, ClaudeLLM)
    assert provider._model_id == "claude-sonnet-4-6"


def test_resolve_llm_canonicalises_vendor_only_form() -> None:
    """``vendor/model`` (no host prefix) is canonicalised before routing."""
    provider = resolve_llm("anthropic/claude-sonnet-4-6")
    assert isinstance(provider, ClaudeLLM)
    assert provider._model_id == "claude-sonnet-4-6"


def test_resolve_llm_rejects_bare_model_id() -> None:
    """Bare vendor slugs (no ``vendor/`` segment) are no longer accepted."""
    with pytest.raises(InvalidModelId):
        resolve_llm("claude-sonnet-4-6")


def test_resolve_llm_routes_google_via_host_table() -> None:
    """``google/<model>`` routes to Gemini via the HOST_TO_PROVIDER table."""
    provider = resolve_llm("google/gemini-3-flash-preview")
    assert isinstance(provider, GeminiLLM)
    assert provider._model_id == "gemini-3-flash-preview"


def test_resolve_llm_routes_openai_via_litellm_host_table() -> None:
    """``openai/<model>`` routes to LiteLLM via the HOST_TO_PROVIDER table.

    Without the LiteLLM branch in :func:`resolve_llm`, this raises
    ``KeyError: "no provider class registered for host <Host.litellm>"``
    at runtime on every OpenAI chat — the HOST_TO_PROVIDER table entry
    is unreachable without the narrowing branch.
    """
    provider = resolve_llm("openai/gpt-4o")
    assert isinstance(provider, LiteLLMLLM)
    assert provider._model == "gpt-4o"
    assert provider._vendor is Vendor.openai


def test_resolve_llm_routes_explicit_litellm_xai_via_host_table() -> None:
    """Explicit ``litellm:xai/<model>`` form routes via LiteLLM.

    The bare ``xai/<model>`` form canonicalises to ``Host.xai`` (the
    native xAI provider, PRs #314/#324) because that path supports
    full reasoning + Live Search.  Callers that need LiteLLM routing
    for xAI specifically must opt in via the fully-qualified
    ``litellm:xai/<model>`` form — this test guards that branch.
    """
    provider = resolve_llm("litellm:xai/grok-3-latest")
    assert isinstance(provider, LiteLLMLLM)
    assert provider._model == "grok-3-latest"
    assert provider._vendor is Vendor.xai


def test_resolve_llm_none_uses_catalog_default() -> None:
    """``model_id=None`` falls back to the catalog's default model."""
    provider = resolve_llm(None)
    # Default is currently a Google model, so we get GeminiLLM. The
    # important assertion is that None doesn't raise.
    assert isinstance(provider, GeminiLLM | ClaudeLLM)


def test_conversation_create_accepts_optional_client_uuid() -> None:
    """ConversationCreate accepts optional frontend-generated UUIDs."""
    conversation_id = uuid4()
    payload = ConversationCreate(id=conversation_id, title="Hello")

    assert payload.id == conversation_id
    assert payload.title == "Hello"


def test_conversation_create_rejects_blank_title() -> None:
    """ConversationCreate enforces non-empty titles when a title is provided."""
    with pytest.raises(ValidationError):
        ConversationCreate(title="   ")


def test_conversation_update_accepts_metadata_only_payload() -> None:
    """ConversationUpdate allows status-only sidebar metadata updates."""
    payload = ConversationUpdate(status="done")

    assert payload.title is None
    assert payload.status == "done"


def test_user_create_strips_invite_code_from_create_update_dict() -> None:
    """Invite codes do not leak into SQLAlchemy user creation payloads."""
    user = UserCreate(
        email="new@example.com",
        password="password123",
        invite_code="secret",
    )

    assert "invite_code" not in user.create_update_dict()
    assert "invite_code" not in user.create_update_dict_superuser()


# ---------------------------------------------------------------------------
# resolve_llm: workspace_id propagation
# ---------------------------------------------------------------------------


def test_resolve_llm_accepts_workspace_root_for_gemini() -> None:
    """resolve_llm with a workspace_root returns a GeminiLLM instance.

    This verifies the workspace_root kwarg is forwarded without blowing up.
    The actual key resolution happens inside GeminiLLM.stream() which is
    tested separately.
    """
    provider = resolve_llm("google/gemini-3-flash-preview", workspace_root=Path(f"/tmp/{uuid4()}"))
    assert isinstance(provider, GeminiLLM)


def test_resolve_llm_accepts_workspace_root_for_claude() -> None:
    """resolve_llm with a workspace_root returns a ClaudeLLM instance."""
    provider = resolve_llm("anthropic/claude-sonnet-4-6", workspace_root=Path(f"/tmp/{uuid4()}"))
    assert isinstance(provider, ClaudeLLM)


def test_resolve_llm_workspace_root_none_is_default() -> None:
    """Passing workspace_root=None (the default) must behave identically to omitting it.

    Both paths must route by model-id prefix; workspace_root only affects key
    resolution inside the provider, not which provider class is returned.
    """
    without = resolve_llm("google/gemini-3-flash-preview")
    with_none = resolve_llm("google/gemini-3-flash-preview", workspace_root=None)

    assert type(without) is type(with_none)


def test_resolve_llm_gemini_accepts_workspace_root_without_error() -> None:
    """resolve_llm(workspace_root=path) for Gemini must not raise AttributeError or TypeError.

    The workspace_root kwarg is forwarded to make_gemini_stream_fn internally;
    this test ensures the forwarding wiring isn't accidentally dropped.
    """
    ws_root = Path(f"/tmp/{uuid4()}")
    # Must not raise.
    provider = resolve_llm("google/gemini-3-flash-preview", workspace_root=ws_root)
    assert isinstance(provider, GeminiLLM)


def test_resolve_llm_claude_provider_stores_workspace_root() -> None:
    """The ClaudeLLM instance returned by resolve_llm carries the workspace_root.

    ClaudeLLM stores workspace_root internally as ``_workspace_root`` and uses
    it during stream() to resolve per-workspace CLAUDE_CODE_OAUTH_TOKEN.
    """
    ws_root = Path(f"/tmp/{uuid4()}")
    provider = resolve_llm("anthropic/claude-sonnet-4-6", workspace_root=ws_root)
    assert isinstance(provider, ClaudeLLM)
    assert provider._workspace_root == ws_root


def test_resolve_llm_claude_propagates_workspace_root_to_cwd(tmp_path) -> None:
    """``workspace_root`` must flow through to ``ClaudeLLMConfig.cwd``.

    Without this, the Claude SDK subprocess runs in the backend's own
    cwd and writes transcript files there — and, under any non-empty
    ``setting_sources``, ingests the host repo's ``CLAUDE.md`` /
    ``.claude/settings.json`` / ``.mcp.json``. The chat router must
    be able to isolate every session by passing the per-user workspace.
    """
    provider = resolve_llm(
        "anthropic/claude-sonnet-4-6",
        workspace_root=tmp_path,
    )
    assert isinstance(provider, ClaudeLLM)
    assert provider._config.cwd == str(tmp_path)


def test_resolve_llm_claude_workspace_root_none_leaves_cwd_unset() -> None:
    """Non-chat callers (LCM, event bus) without a workspace_root see ``cwd=None``.

    They rely on the provider's unconditional ``setting_sources=[]`` to
    keep filesystem sources off — ``cwd`` is just the transcript
    location for them.
    """
    provider = resolve_llm("anthropic/claude-sonnet-4-6")
    assert isinstance(provider, ClaudeLLM)
    assert provider._config.cwd is None


# ---------------------------------------------------------------------------
# resolve_api_key end-to-end: workspace override beats settings
# ---------------------------------------------------------------------------


def test_resolve_api_key_workspace_override_beats_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """resolve_api_key returns the per-user workspace override over settings.

    This is the load-bearing contract for the workspace env feature:
    a user who sets their own GEMINI_API_KEY gets their key used, not
    the gateway-wide key.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    monkeypatch.setattr(settings, "google_api_key", "gateway-key")

    uid = uuid4()
    ws_root = tmp_path / str(uid)
    keys.save_workspace_env(ws_root, {"GEMINI_API_KEY": "my-personal-gemini-key"})

    result = keys.resolve_api_key(ws_root, "GEMINI_API_KEY")
    assert result == "my-personal-gemini-key", f"Expected workspace override to win; got {result!r}"


def test_resolve_api_key_falls_back_to_settings_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """resolve_api_key falls back to settings when the user has no override.

    A brand-new user (no workspace env file yet) gets the gateway key.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    monkeypatch.setattr(settings, "exa_api_key", "gateway-exa")

    uid = uuid4()  # User with no saved env.
    ws_root = tmp_path / str(uid)
    result = keys.resolve_api_key(ws_root, "EXA_API_KEY")
    assert result == "gateway-exa"


def test_resolve_api_key_cleared_override_reverts_to_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Saving an empty-string value clears the override; settings is used again.

    The UI sends empty string when a user clears an input. After clear,
    the user should see the same key as everyone else.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    monkeypatch.setattr(settings, "exa_api_key", "gateway-exa")

    uid = uuid4()
    ws_root = tmp_path / str(uid)
    # Set an override first.
    keys.save_workspace_env(ws_root, {"EXA_API_KEY": "my-exa"})
    assert keys.resolve_api_key(ws_root, "EXA_API_KEY") == "my-exa"

    # Clear it by saving empty string.
    keys.save_workspace_env(ws_root, {"EXA_API_KEY": ""})
    # Now falls back to settings.
    assert keys.resolve_api_key(ws_root, "EXA_API_KEY") == "gateway-exa"


def test_resolve_api_key_two_users_are_isolated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Each user's workspace env is independent from others.

    User A's key must never leak into user B's resolution.
    """
    monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
    monkeypatch.setattr(settings, "exa_api_key", "gateway-exa")

    uid_a = uuid4()
    uid_b = uuid4()

    ws_root_a = tmp_path / str(uid_a)
    ws_root_b = tmp_path / str(uid_b)

    keys.save_workspace_env(ws_root_a, {"EXA_API_KEY": "user-a-exa"})
    # User B has no override.

    assert keys.resolve_api_key(ws_root_a, "EXA_API_KEY") == "user-a-exa"
    assert keys.resolve_api_key(ws_root_b, "EXA_API_KEY") == "gateway-exa"

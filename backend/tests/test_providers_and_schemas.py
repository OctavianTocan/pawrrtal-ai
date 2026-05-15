"""Tests for provider routing, workspace-env key resolution, and schema behavior.

This module covers:
- :func:`resolve_llm` routing (model-id prefix → provider class)
- :func:`resolve_llm` workspace_id propagation to providers (workspace env support)
- Schema validation for :class:`ConversationCreate`, :class:`ConversationUpdate`,
  :class:`UserCreate`
- :func:`resolve_api_key` precedence (workspace override > settings fallback)
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core import keys
from app.core.config import settings
from app.core.providers.claude_provider import ClaudeLLM
from app.core.providers.factory import resolve_llm
from app.core.providers.gemini_provider import GeminiLLM
from app.core.providers.model_id import InvalidModelId
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


def test_resolve_llm_accepts_workspace_id_for_gemini() -> None:
    """resolve_llm with a workspace_id returns a GeminiLLM instance.

    This verifies the new workspace_id kwarg is forwarded without blowing up.
    The actual key resolution happens inside GeminiLLM.stream() which is
    tested separately.
    """
    provider = resolve_llm("google/gemini-3-flash-preview", workspace_id=uuid4())
    assert isinstance(provider, GeminiLLM)


def test_resolve_llm_accepts_workspace_id_for_claude() -> None:
    """resolve_llm with a workspace_id returns a ClaudeLLM instance."""
    provider = resolve_llm("anthropic/claude-sonnet-4-6", workspace_id=uuid4())
    assert isinstance(provider, ClaudeLLM)


def test_resolve_llm_workspace_id_none_is_default() -> None:
    """Passing workspace_id=None (the default) must behave identically to omitting it.

    Both paths must route by model-id prefix; workspace_id only affects key
    resolution inside the provider, not which provider class is returned.
    """
    without = resolve_llm("google/gemini-3-flash-preview")
    with_none = resolve_llm("google/gemini-3-flash-preview", workspace_id=None)

    assert type(without) is type(with_none)


def test_resolve_llm_gemini_accepts_workspace_id_without_error() -> None:
    """resolve_llm(workspace_id=uid) for Gemini must not raise AttributeError or TypeError.

    The workspace_id kwarg is forwarded to make_gemini_stream_fn internally;
    this test ensures the forwarding wiring isn't accidentally dropped.
    """
    uid = uuid4()
    # Must not raise.
    provider = resolve_llm("google/gemini-3-flash-preview", workspace_id=uid)
    assert isinstance(provider, GeminiLLM)


def test_resolve_llm_claude_provider_stores_workspace_id() -> None:
    """The ClaudeLLM instance returned by resolve_llm carries the workspace_id.

    ClaudeLLM stores workspace_id internally as ``_workspace_id`` and uses it
    during stream() to resolve per-workspace CLAUDE_CODE_OAUTH_TOKEN.
    """
    uid = uuid4()
    provider = resolve_llm("anthropic/claude-sonnet-4-6", workspace_id=uid)
    assert isinstance(provider, ClaudeLLM)
    assert provider._workspace_id == uid


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
    keys.save_workspace_env(uid, {"GEMINI_API_KEY": "my-personal-gemini-key"})

    result = keys.resolve_api_key(uid, "GEMINI_API_KEY")
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
    result = keys.resolve_api_key(uid, "EXA_API_KEY")
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
    # Set an override first.
    keys.save_workspace_env(uid, {"EXA_API_KEY": "my-exa"})
    assert keys.resolve_api_key(uid, "EXA_API_KEY") == "my-exa"

    # Clear it by saving empty string.
    keys.save_workspace_env(uid, {"EXA_API_KEY": ""})
    # Now falls back to settings.
    assert keys.resolve_api_key(uid, "EXA_API_KEY") == "gateway-exa"


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

    keys.save_workspace_env(uid_a, {"EXA_API_KEY": "user-a-exa"})
    # User B has no override.

    assert keys.resolve_api_key(uid_a, "EXA_API_KEY") == "user-a-exa"
    assert keys.resolve_api_key(uid_b, "EXA_API_KEY") == "gateway-exa"

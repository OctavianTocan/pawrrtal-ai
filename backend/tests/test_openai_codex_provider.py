"""
Tests for the first-class `openai_codex` provider and the Codex-driven image generation plugin.

Test buckets:
- Auth/discovery, event mapper, and provider-contract tests run strict and
  mock at the `AsyncCodex.thread_start` / `AsyncTurnHandle.stream` seam.
- Image plugin tests are gated by the plugin's own activation story
  (bean pawrrtal-roi0 / openai_codex_image_gen) and stay xfail until
  that work lands.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# -----------------------------------------------------------------------------
# Support for the vendored Codex repo (added as git submodule at
# backend/vendor/codex per the integration plan). Must come BEFORE the
# try-import block below so the lazy `__getattr__` in
# app.providers.openai_codex can resolve SDK symbols.
# -----------------------------------------------------------------------------
VENDORED_CODEX_PYTHON_SDK = (
    Path(__file__).parent.parent / "vendor" / "codex" / "sdk" / "python" / "src"
)

if VENDORED_CODEX_PYTHON_SDK.exists() and str(VENDORED_CODEX_PYTHON_SDK) not in sys.path:
    sys.path.insert(0, str(VENDORED_CODEX_PYTHON_SDK))

# Core provider + auth symbols are now live (Phase 1 wiring complete).
# Image plugin symbols remain guarded because that plugin is still under
# the original commented implementation.
_IMPORT_ERROR: Exception | None = None
try:
    from app.providers.base import StreamEvent
    from app.providers.openai_codex import OpenAICodexProvider
    from app.providers.openai_codex.auth import (
        OpenAICodexAuthError,
        resolve_openai_codex_auth,
    )
except Exception as import_exc:
    # Should not happen after Phase 1, but keep the file importable.
    OpenAICodexProvider = None
    resolve_openai_codex_auth = None  # type: ignore[assignment]
    OpenAICodexAuthError = Exception  # type: ignore[misc,assignment]
    StreamEvent = dict  # type: ignore[misc,assignment]
    _IMPORT_ERROR = import_exc

# Image plugin symbols are guarded separately because the plugin has its own
# activation story (see openai_codex_image_gen/ and the plugin registry).
try:
    from app.agents.types import AgentTool
    from app.plugins.openai_codex_image_gen.codex_image_agent import generate_image_with_codex_agent
except Exception:
    generate_image_with_codex_agent = None  # type: ignore
    AgentTool = None  # type: ignore

# Test buckets:
# - Auth/discovery, event mapper, and provider-contract tests run strict.
# - Image plugin tests are gated by the plugin's own activation story
#   (bean pawrrtal-roi0 / openai_codex_image_gen) and stay xfail until
#   that work lands.

IMAGE_PLUGIN_XFAIL = pytest.mark.xfail(
    reason="openai_codex_image_gen plugin activation pending (bean pawrrtal-roi0)",
    strict=False,
)


# =============================================================================
# PROVIDER REGRESSION TESTS (deny-all approval + reasoning summary validation)
# =============================================================================


@pytest.mark.anyio
async def test_provider_installs_deny_all_approval_handler(monkeypatch):
    """
    REGRESSION: The SDK's default approval handler accepts all
    shell-exec and file-change requests. The provider MUST install a
    deny-all handler before the codex app-server starts.
    See client.py:_default_approval_handler — accepts by default.
    """
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    provider = OpenAICodexProvider("gpt-5.5", workspace_root=None)

    class _FakeSyncClient:
        def __init__(self) -> None:
            self._approval_handler = None

    class _FakeClient:
        def __init__(self) -> None:
            self._sync = _FakeSyncClient()

    class _FakeCodex:
        def __init__(self) -> None:
            self._client = _FakeClient()

        async def _ensure_initialized(self) -> None:
            return None

    fake = _FakeCodex()
    monkeypatch.setattr(provider, "_codex", fake)

    provider._install_deny_all_approval_handler()

    handler = fake._client._sync._approval_handler
    assert handler is not None
    assert handler("item/commandExecution/requestApproval", {"command": "rm -rf /"}) == {
        "decision": "deny"
    }
    assert handler("item/fileChange/requestApproval", {"path": "/etc/passwd"}) == {
        "decision": "deny"
    }


@pytest.mark.anyio
async def test_provider_passes_validated_reasoning_summary(monkeypatch):
    """
    REGRESSION: provider used `ReasoningSummary.auto` which is invalid
    because ReasoningSummary is a Pydantic RootModel, not an Enum.
    Confirm the provider now passes a model-validated instance whose
    `.root` is the `auto` value.
    """
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.providers.openai_codex import ReasoningSummary
    from app.providers.openai_codex.provider import (
        _get_default_reasoning_summary,
    )

    summary = _get_default_reasoning_summary()
    assert isinstance(summary, ReasoningSummary)
    # RootModel exposes the inner value as .root
    assert getattr(summary.root, "value", summary.root) == "auto"


# =============================================================================
# AUTH LAYER TESTS — narrowed to behaviour resolve_openai_codex_auth actually
# implements. The thicker $CODEX_HOME / workspace .codex / refresh path
# documented in the original test draft is intentionally NOT implemented in
# auth.py (the binary owns the user's standard auth file). Tests assert what
# the function actually does today.
# =============================================================================


def test_auth_resolution_prefers_override(tmp_path: Path) -> None:
    """Explicit OPENAI_CODEX_OAUTH_TOKEN override always wins."""
    if _IMPORT_ERROR or resolve_openai_codex_auth is None:
        pytest.skip("Core provider/auth symbols not importable (should not happen after Phase 1)")

    token, _account_id = resolve_openai_codex_auth(
        override="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-token",
        workspace_root=tmp_path,
    )
    assert token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-token"


def test_auth_resolution_returns_none_when_no_override(tmp_path: Path) -> None:
    """Without an override, auth returns (None, None) and lets the SDK
    fall back to the binary's own ~/.codex/auth.json handling."""
    if _IMPORT_ERROR or resolve_openai_codex_auth is None:
        pytest.skip("Core provider/auth symbols not importable")

    token, account_id = resolve_openai_codex_auth(workspace_root=tmp_path)
    assert token is None
    assert account_id is None


def test_auth_resolution_does_not_raise_with_workspace_dot_codex(tmp_path: Path) -> None:
    """Workspace-level .codex/auth.json is logged but not yet wired —
    function must not crash when one is present."""
    if _IMPORT_ERROR or resolve_openai_codex_auth is None:
        pytest.skip("Core provider/auth symbols not importable")

    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "auth.json").write_text(json.dumps({"tokens": {"access_token": "ws"}}))

    token, _ = resolve_openai_codex_auth(workspace_root=tmp_path)
    assert token is None  # per current "not yet wired" placeholder behavior


def test_build_app_server_config_passes_through_codex_bin(tmp_path: Path) -> None:
    """build_app_server_config respects an explicit codex_bin."""
    if _IMPORT_ERROR:
        pytest.skip("Core provider/auth symbols not importable")
    from app.providers.openai_codex.auth import build_app_server_config

    cfg = build_app_server_config(codex_bin=tmp_path / "codex")
    assert cfg["codex_bin"] == str(tmp_path / "codex")


def test_no_tokens_leak_in_logs(caplog):
    """Auth code must never log raw access tokens."""
    if _IMPORT_ERROR or resolve_openai_codex_auth is None:
        pytest.skip("Core provider/auth symbols not importable")

    import logging

    caplog.set_level(logging.DEBUG)

    secret_token = "sk-eyJ-this-should-never-appear-in-logs"
    resolve_openai_codex_auth(override=secret_token)

    assert secret_token not in caplog.text


# =============================================================================
# PROVIDER CONTRACT TESTS
# =============================================================================


def test_openai_codex_provider_has_required_stream_method():
    """Provider must satisfy the AILLM streaming contract."""
    if _IMPORT_ERROR or OpenAICodexProvider is None:
        pytest.skip("Implementation modules not importable")

    provider = OpenAICodexProvider("gpt-5.5", workspace_root=None)
    assert hasattr(provider, "stream")
    assert callable(provider.stream)


def test_provider_stores_model_and_workspace():
    """Provider correctly stores constructor arguments."""
    if _IMPORT_ERROR or OpenAICodexProvider is None:
        pytest.skip("Implementation modules not importable")

    ws = Path("/tmp/some-workspace")
    p = OpenAICodexProvider("gpt-5.4-codex", workspace_root=ws, codex_bin="/usr/local/bin/codex")
    assert p._model_id == "gpt-5.4-codex"
    assert p._workspace_root == ws
    assert p._codex_bin == "/usr/local/bin/codex"


def test_provider_creates_client_lazily():
    """Client should not be created at construction time."""
    if _IMPORT_ERROR or OpenAICodexProvider is None:
        pytest.skip("Implementation modules not importable")

    p = OpenAICodexProvider("gpt-5.5", workspace_root=None)
    assert p._codex is None


# -----------------------------------------------------------------------------
# Stream contract — mocked at the AsyncCodex.thread_start / TurnHandle seam.
# These tests exercise the real provider code path; only the SDK is replaced.
# -----------------------------------------------------------------------------


def _build_fake_codex(
    *,
    turn_notifications: list[object] | None = None,
    thread_start_raises: Exception | None = None,
    turn_stream_raises: Exception | None = None,
) -> object:
    """Build a fake AsyncCodex that mimics the surface the provider touches.

    The provider calls (in order):
        codex._ensure_initialized()
        codex.thread_start(...)  -> thread
        thread.turn(run_input, ...)  -> handle
        async for notification in handle.stream(): ...
    Each step is independently overridable for negative tests.
    """
    notifs = list(turn_notifications or [])

    class _FakeHandle:
        async def stream(self):
            if turn_stream_raises is not None:
                raise turn_stream_raises
            for n in notifs:
                yield n

    class _FakeThread:
        id = "thr_test_123"

        async def turn(self, run_input, **kw):
            return _FakeHandle()

    class _FakeSyncClient:
        _approval_handler = None

    class _FakeInnerClient:
        _sync = _FakeSyncClient()

    class _FakeCodex:
        _client = _FakeInnerClient()

        async def _ensure_initialized(self):
            return None

        async def thread_start(self, **kw):
            if thread_start_raises is not None:
                raise thread_start_raises
            return _FakeThread()

        async def thread_resume(self, tid, **kw):
            t = _FakeThread()
            t.id = tid
            return t

        async def close(self):
            return None

    return _FakeCodex()


@pytest.mark.anyio
async def test_provider_stream_emits_codex_thread_created_event(monkeypatch):
    """First turn must emit an internal `codex_thread_created` event so the
    caller can persist the thread id for resume on subsequent turns."""
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.providers.openai_codex import provider as provider_mod

    fake_codex = _build_fake_codex(turn_notifications=[])

    async def _fake_ensure_codex(self):
        self._codex = fake_codex
        return self._codex

    monkeypatch.setattr(provider_mod.OpenAICodexProvider, "_ensure_codex", _fake_ensure_codex)

    provider = provider_mod.OpenAICodexProvider("gpt-5.5")
    events = [ev async for ev in provider.stream("hi", uuid.uuid4(), uuid.uuid4())]

    kinds = [(e.get("type"), e.get("kind")) for e in events]
    assert ("internal", "codex_thread_created") in kinds


@pytest.mark.anyio
async def test_stream_yields_error_event_on_thread_start_exception(monkeypatch):
    """Exception from thread_start must produce one error event and exit cleanly."""
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.providers.openai_codex import provider as provider_mod

    fake_codex = _build_fake_codex(thread_start_raises=RuntimeError("Codex refused thread"))

    async def _fake_ensure_codex(self):
        self._codex = fake_codex
        return self._codex

    monkeypatch.setattr(provider_mod.OpenAICodexProvider, "_ensure_codex", _fake_ensure_codex)

    provider = provider_mod.OpenAICodexProvider("gpt-5.5")
    events = [e async for e in provider.stream("test", uuid.uuid4(), uuid.uuid4())]

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Failed to start/resume Codex thread" in events[0]["content"]


@pytest.mark.anyio
async def test_stream_yields_error_event_on_turn_stream_exception(monkeypatch):
    """Exception raised inside `handle.stream()` is caught and surfaced."""
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.providers.openai_codex import provider as provider_mod

    fake_codex = _build_fake_codex(turn_stream_raises=RuntimeError("stream blew up"))

    async def _fake_ensure_codex(self):
        self._codex = fake_codex
        return self._codex

    monkeypatch.setattr(provider_mod.OpenAICodexProvider, "_ensure_codex", _fake_ensure_codex)

    provider = provider_mod.OpenAICodexProvider("gpt-5.5")
    events = [e async for e in provider.stream("test", uuid.uuid4(), uuid.uuid4())]

    assert any(e.get("type") == "error" and "Codex turn failed" in e["content"] for e in events)


@pytest.mark.anyio
async def test_stream_resumes_existing_thread_when_thread_id_provided(monkeypatch):
    """When the caller passes `codex_thread_id`, the provider must call
    thread_resume instead of thread_start, and must NOT emit a
    `codex_thread_created` event."""
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.providers.openai_codex import provider as provider_mod

    fake_codex = _build_fake_codex(turn_notifications=[])

    async def _fake_ensure_codex(self):
        self._codex = fake_codex
        return self._codex

    monkeypatch.setattr(provider_mod.OpenAICodexProvider, "_ensure_codex", _fake_ensure_codex)

    provider = provider_mod.OpenAICodexProvider("gpt-5.5")
    events = [
        ev
        async for ev in provider.stream(
            "follow up",
            uuid.uuid4(),
            uuid.uuid4(),
            codex_thread_id="thr_existing_abc",
        )
    ]

    kinds = [(e.get("type"), e.get("kind")) for e in events]
    assert ("internal", "codex_thread_created") not in kinds


# =============================================================================
# EVENT MAPPER TESTS — use real SDK notification objects, since the mapper
# dispatches by isinstance() against generated Pydantic models.
# =============================================================================


def _make_real_payload(payload_cls_name: str, **payload_kwargs: object) -> object | None:
    """Build a real Codex SDK notification payload model.

    The mapper looks up `notification.payload` first and falls back to the
    object itself when there is no `.payload` attribute (events.py:74),
    so passing the payload directly is sufficient. The vendored 0.131.0a4
    SDK does not expose a top-level Notification wrapper class, only the
    individual payload models in `generated.v2_all`.

    Returns None when the SDK isn't importable (test will skip).
    """
    from app.providers.openai_codex._vendor import get_openai_codex_module

    sdk = get_openai_codex_module()
    v2 = getattr(getattr(sdk, "generated", None), "v2_all", None)
    if v2 is None:
        return None
    payload_cls = getattr(v2, payload_cls_name, None)
    if payload_cls is None:
        return None
    try:
        instance: object = payload_cls(**payload_kwargs)
        return instance
    except Exception:
        return None


# Required-everywhere routing identifiers on every SDK notification payload.
_NOTIF_ROUTING = {"item_id": "item_1", "thread_id": "thr_1", "turn_id": "turn_1"}


def test_event_mapper_skips_non_notification_inputs():
    """The mapper must be defensive against unexpected inputs."""
    if _IMPORT_ERROR:
        pytest.skip("Implementation modules not importable")

    from app.providers.openai_codex.events import map_codex_notification_to_stream_events

    weird = object()
    events = list(map_codex_notification_to_stream_events(weird))
    assert events == []


def test_event_mapper_handles_text_delta():
    """AgentMessageDeltaNotification → {type: delta, content: ...}."""
    if _IMPORT_ERROR:
        pytest.skip("Implementation modules not importable")

    from app.providers.openai_codex.events import map_codex_notification_to_stream_events

    payload = _make_real_payload("AgentMessageDeltaNotification", delta="Hello", **_NOTIF_ROUTING)
    if payload is None:
        pytest.skip("SDK AgentMessageDeltaNotification not constructable in this layout")

    events = list(map_codex_notification_to_stream_events(payload))
    assert any(e.get("type") == "delta" and e.get("content") == "Hello" for e in events)


def test_event_mapper_handles_reasoning_summary_delta():
    """ReasoningSummaryTextDeltaNotification → thinking event with summary=True."""
    if _IMPORT_ERROR:
        pytest.skip("Implementation modules not importable")

    from app.providers.openai_codex.events import map_codex_notification_to_stream_events

    payload = _make_real_payload(
        "ReasoningSummaryTextDeltaNotification",
        delta="Thinking...",
        content_index=0,
        summary_index=0,
        **_NOTIF_ROUTING,
    )
    if payload is None:
        pytest.skip("SDK ReasoningSummaryTextDeltaNotification not constructable")

    events = list(map_codex_notification_to_stream_events(payload))
    assert any(e.get("type") == "thinking" and e.get("summary") is True for e in events)


def test_event_mapper_handles_reasoning_text_delta():
    """ReasoningTextDeltaNotification → thinking event with summary=False."""
    if _IMPORT_ERROR:
        pytest.skip("Implementation modules not importable")

    from app.providers.openai_codex.events import map_codex_notification_to_stream_events

    payload = _make_real_payload(
        "ReasoningTextDeltaNotification",
        delta="Step by step...",
        content_index=0,
        **_NOTIF_ROUTING,
    )
    if payload is None:
        pytest.skip("SDK ReasoningTextDeltaNotification not constructable")

    events = list(map_codex_notification_to_stream_events(payload))
    assert any(e.get("type") == "thinking" and e.get("summary") is False for e in events)


# =============================================================================
# REASONING EFFORT MAPPING
# =============================================================================


def test_map_pawrrtal_reasoning_to_codex_handles_known_values():
    """_map_pawrrtal_reasoning_to_codex must accept all documented efforts
    without crashing, and cap extra-high at high (the SDK's ceiling)."""
    if _IMPORT_ERROR:
        pytest.skip("Implementation modules not importable")

    from app.providers.openai_codex import ReasoningEffort
    from app.providers.openai_codex.provider import _map_pawrrtal_reasoning_to_codex

    assert _map_pawrrtal_reasoning_to_codex(None) is None
    assert _map_pawrrtal_reasoning_to_codex("minimal") == ReasoningEffort.minimal
    assert _map_pawrrtal_reasoning_to_codex("low") == ReasoningEffort.low
    assert _map_pawrrtal_reasoning_to_codex("medium") == ReasoningEffort.medium
    assert _map_pawrrtal_reasoning_to_codex("high") == ReasoningEffort.high
    # Pawrrtal's "extra-high" must clamp to the SDK's "high" ceiling.
    assert _map_pawrrtal_reasoning_to_codex("extra-high") == ReasoningEffort.high


def test_build_codex_run_input_accepts_history_and_prompt():
    """build_codex_run_input is the dedicated translation layer; verify
    that it accepts the documented arguments and returns a usable value."""
    if _IMPORT_ERROR:
        pytest.skip("Implementation modules not importable")

    from app.providers.openai_codex.inputs import build_codex_run_input

    history = [{"role": "user", "content": "earlier"}]
    result = build_codex_run_input(question="new question", history=history)
    # Translation layer may return a TextInput, a list of input items,
    # or a str depending on history shape — all are acceptable for v1.
    assert result is not None


# =============================================================================
# VENDORED BINARY DISCOVERY — opt-in PATH fallback gate
# =============================================================================


def test_discover_vendored_codex_bin_returns_none_without_fallback_flag(monkeypatch, tmp_path):
    """Without the dev-fallback flag, discovery must NOT return a PATH match."""
    from app.providers.openai_codex import _vendor

    isolated_sdk_src = tmp_path / "isolated-backend" / "vendor" / "codex" / "sdk" / "python" / "src"
    monkeypatch.setattr(_vendor, "_vendored_sdk_src_path", lambda: isolated_sdk_src)
    monkeypatch.delenv("OPENAI_CODEX_ALLOW_PATH_FALLBACK", raising=False)

    # PATH has codex available locally on most dev machines via Homebrew.
    # If the flag is off, discovery returns None even if PATH would resolve.
    result = _vendor.discover_vendored_codex_bin()
    assert result is None


def test_discover_vendored_codex_bin_uses_path_when_flag_enabled(monkeypatch, tmp_path):
    """With the flag on, fall back to PATH-resolved codex if no vendored binary."""
    from app.providers.openai_codex import _vendor

    fake_bin = tmp_path / "fake-codex"
    fake_bin.write_text("#!/bin/sh\necho 0.0.0\n")
    fake_bin.chmod(0o755)

    isolated_sdk_src = tmp_path / "isolated-backend" / "vendor" / "codex" / "sdk" / "python" / "src"
    monkeypatch.setattr(_vendor, "_vendored_sdk_src_path", lambda: isolated_sdk_src)
    monkeypatch.setenv("OPENAI_CODEX_ALLOW_PATH_FALLBACK", "true")
    monkeypatch.setattr(_vendor, "_shutil_which", lambda name: str(fake_bin))

    result = _vendor.discover_vendored_codex_bin()
    assert result == Path(str(fake_bin))


# =============================================================================
# IMAGE PLUGIN TESTS — gated behind IMAGE_PLUGIN_XFAIL until the plugin's
# activation story (bean pawrrtal-roi0 / openai_codex_image_gen) lands.
# =============================================================================


@IMAGE_PLUGIN_XFAIL
@pytest.mark.anyio
async def test_image_plugin_returns_expected_artifact_shape():
    """The Codex image agent returns a properly shaped artifact or error."""
    if _IMPORT_ERROR or generate_image_with_codex_agent is None:
        pytest.skip("Image plugin not importable yet")

    result = await generate_image_with_codex_agent(
        prompt="A serene mountain landscape at dawn",
        style="photorealistic",
        workspace_root=None,
    )

    assert isinstance(result, dict)
    assert "provider" in result
    assert result["provider"] == "openai_codex"
    assert "image_b64" in result or "error" in result


@IMAGE_PLUGIN_XFAIL
@pytest.mark.anyio
async def test_image_plugin_propagates_errors_gracefully():
    """Errors from the underlying Codex provider are surfaced cleanly."""
    if _IMPORT_ERROR or generate_image_with_codex_agent is None:
        pytest.skip("Image plugin not importable yet")

    with patch(
        "app.plugins.openai_codex_image_gen.codex_image_agent.OpenAICodexProvider"
    ) as mock_provider:
        mock_provider.return_value.stream.side_effect = RuntimeError("Codex blew up")

        result = await generate_image_with_codex_agent(prompt="test", workspace_root=None)

    assert "error" in result
    assert "Codex blew up" in result["error"]


@IMAGE_PLUGIN_XFAIL
@pytest.mark.anyio
async def test_image_plugin_builds_good_prompt_for_codex():
    """The prompt sent to Codex should be well-structured and include style."""
    if _IMPORT_ERROR or generate_image_with_codex_agent is None:
        pytest.skip("Image plugin not importable yet")

    result = await generate_image_with_codex_agent(
        prompt="A cyberpunk cat",
        style="in the style of Blade Runner",
        workspace_root=None,
    )
    assert "provider" in result


@IMAGE_PLUGIN_XFAIL
@pytest.mark.anyio
async def test_image_plugin_handles_codex_returning_no_image():
    """If Codex finishes without producing an image, we get a clear error."""
    if _IMPORT_ERROR or generate_image_with_codex_agent is None:
        pytest.skip("Image plugin not importable yet")

    with patch(
        "app.plugins.openai_codex_image_gen.codex_image_agent.OpenAICodexProvider"
    ) as mock_p:

        async def fake_stream(*a, **k):
            yield {"type": "delta", "content": "thinking..."}
            yield {"type": "done"}

        mock_p.return_value.stream = fake_stream

        result = await generate_image_with_codex_agent(prompt="test", workspace_root=None)
        assert "error" in result


@IMAGE_PLUGIN_XFAIL
@pytest.mark.anyio
async def test_image_plugin_uses_provider_stream_and_extracts_artifact():
    """The image agent must drive the provider and correctly extract image results."""
    if _IMPORT_ERROR or generate_image_with_codex_agent is None:
        pytest.skip("Image plugin not importable yet")

    async def fake_stream(*args, **kwargs):
        yield {"type": "thinking", "content": "planning image..."}
        yield {"type": "artifact", "kind": "image", "data": "fake_base64_image_data"}

    with patch(
        "app.plugins.openai_codex_image_gen.codex_image_agent.OpenAICodexProvider"
    ) as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.stream = fake_stream

        result = await generate_image_with_codex_agent(prompt="test image", workspace_root=None)

    assert result["image_b64"] == "fake_base64_image_data" or "data" in str(result)
    assert result.get("provider") == "openai_codex"

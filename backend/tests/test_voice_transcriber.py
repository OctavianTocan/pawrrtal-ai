"""Tests for ``app.integrations.voice.transcriber``.

Focused on the wiring most likely to regress:

* The xAI HTTP transcriber sends the expected multipart body, decodes
  the ``text`` field, and raises ``TranscriptionError`` on non-2xx.
* ``resolve_transcriber()`` builds an ``XaiSttTranscriber`` when
  ``voice_provider == "xai"`` and ``settings.xai_api_key`` is set,
  and returns ``None`` when the key is missing.  Mistral / OpenAI /
  local branches preserve their previous behaviour.

Closes the bug where Telegram voice notes silently skipped
transcription when the deployment used the (default) xAI backend.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.integrations.voice import (
    LocalWhisperCppTranscriber,
    MistralVoxtralTranscriber,
    OpenAIWhisperTranscriber,
    TranscriptionError,
    XaiSttTranscriber,
    resolve_transcriber,
)
from app.integrations.voice import transcriber as transcriber_module

pytestmark = pytest.mark.anyio


@pytest.fixture
def restore_voice_settings() -> Generator[None]:
    """Snapshot voice-related ``Settings`` fields and restore after the test."""
    snapshot = {
        "voice_provider": settings.voice_provider,
        "xai_api_key": settings.xai_api_key,
        "voice_mistral_api_key": settings.voice_mistral_api_key,
        "voice_openai_api_key": settings.voice_openai_api_key,
        "voice_whisper_cpp_binary": settings.voice_whisper_cpp_binary,
        "voice_whisper_cpp_model": settings.voice_whisper_cpp_model,
    }
    try:
        yield
    finally:
        for key, value in snapshot.items():
            setattr(settings, key, value)


class _StubResponse:
    """Minimal ``httpx.Response``-like object usable from a stub transport."""

    def __init__(self, status_code: int, payload: Any | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def _install_stub_post(
    monkeypatch: pytest.MonkeyPatch,
    response: _StubResponse,
    *,
    captured: dict[str, Any] | None = None,
) -> None:
    """Patch ``httpx.AsyncClient.post`` to return ``response`` deterministically.

    When ``captured`` is supplied the patched method records the URL,
    headers, data, and files it received so the test can assert on the
    actual request shape.
    """

    async def _post(self: Any, url: str, **kwargs: Any) -> _StubResponse:
        if captured is not None:
            captured["url"] = url
            captured.update(kwargs)
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)


class TestXaiSttTranscriber:
    async def test_returns_text_field_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}
        _install_stub_post(
            monkeypatch,
            _StubResponse(200, payload={"text": "hello world"}),
            captured=captured,
        )
        transcriber = XaiSttTranscriber(api_key="sk-test", language="en")
        text = await transcriber.transcribe(b"OggS\x00fake")
        assert text == "hello world"
        # Verify the request shape matches xAI's expectations.
        assert captured["url"] == transcriber_module.XAI_STT_URL
        assert captured["headers"]["Authorization"] == "Bearer sk-test"
        assert captured["data"]["language"] == "en"
        assert captured["data"]["format"] == "true"
        # ``file`` is the documented last multipart field.
        assert "file" in captured["files"]

    async def test_omits_language_field_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}
        _install_stub_post(
            monkeypatch,
            _StubResponse(200, payload={"text": "hi"}),
            captured=captured,
        )
        transcriber = XaiSttTranscriber(api_key="sk-test")
        await transcriber.transcribe(b"voice")
        assert "language" not in captured["data"]
        assert captured["data"]["format"] == "true"

    async def test_raises_on_non_2xx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_stub_post(monkeypatch, _StubResponse(429, text="rate limited"), captured=None)
        transcriber = XaiSttTranscriber(api_key="sk-test")
        with pytest.raises(TranscriptionError) as excinfo:
            await transcriber.transcribe(b"voice")
        assert "429" in str(excinfo.value)
        assert "rate limited" in str(excinfo.value)

    async def test_raises_on_empty_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_stub_post(monkeypatch, _StubResponse(200, payload={"text": "   "}))
        transcriber = XaiSttTranscriber(api_key="sk-test")
        with pytest.raises(TranscriptionError) as excinfo:
            await transcriber.transcribe(b"voice")
        assert "empty" in str(excinfo.value).lower()

    async def test_raises_on_request_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _explode(self: Any, url: str, **kwargs: Any) -> _StubResponse:
            raise httpx.ConnectError("dns failure")

        monkeypatch.setattr(httpx.AsyncClient, "post", _explode)
        transcriber = XaiSttTranscriber(api_key="sk-test")
        with pytest.raises(TranscriptionError):
            await transcriber.transcribe(b"voice")


class TestResolveTranscriber:
    def test_xai_branch_returns_transcriber_when_global_key_set(
        self, restore_voice_settings: None
    ) -> None:
        settings.voice_provider = "xai"
        settings.xai_api_key = "sk-global"
        built = resolve_transcriber()
        assert isinstance(built, XaiSttTranscriber)

    def test_xai_branch_returns_none_when_key_missing(self, restore_voice_settings: None) -> None:
        settings.voice_provider = "xai"
        settings.xai_api_key = ""
        assert resolve_transcriber() is None

    def test_mistral_branch_returns_transcriber_when_key_set(
        self, restore_voice_settings: None
    ) -> None:
        settings.voice_provider = "mistral"
        settings.voice_mistral_api_key = "mk-test"
        assert isinstance(resolve_transcriber(), MistralVoxtralTranscriber)

    def test_openai_branch_returns_transcriber_when_key_set(
        self, restore_voice_settings: None
    ) -> None:
        settings.voice_provider = "openai"
        settings.voice_openai_api_key = "ok-test"
        assert isinstance(resolve_transcriber(), OpenAIWhisperTranscriber)

    def test_local_branch_returns_transcriber(self, restore_voice_settings: None) -> None:
        settings.voice_provider = "local"
        settings.voice_whisper_cpp_binary = ""
        settings.voice_whisper_cpp_model = "base"
        assert isinstance(resolve_transcriber(), LocalWhisperCppTranscriber)

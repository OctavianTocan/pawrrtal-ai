"""Tests for the pluggable voice-transcription backends (#374).

Specifically covers the seam ``resolve_transcriber(include_xai=...)``
introduced for the Telegram voice-note path so a default
``voice_provider=xai`` deployment actually transcribes rather than
silently dropping voice notes with "ask the user to retype".
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.integrations.voice import (
    XaiSttTranscriber,
    resolve_transcriber,
)


def test_resolve_transcriber_returns_none_for_xai_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backwards-compatible default: the api/stt.py web route keeps its own xAI path.

    ``include_xai=False`` (the default) preserves the historical
    contract — the web composer route owns the xAI call so it can
    resolve a workspace-level ``XAI_API_KEY`` override.
    """
    monkeypatch.setattr(settings, "voice_provider", "xai")
    monkeypatch.setattr(settings, "xai_api_key", "test-xai-key")
    assert resolve_transcriber() is None


def test_resolve_transcriber_returns_xai_when_include_xai_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telegram opts in via ``include_xai=True`` so voice notes transcribe (#374)."""
    monkeypatch.setattr(settings, "voice_provider", "xai")
    monkeypatch.setattr(settings, "xai_api_key", "test-xai-key")
    transcriber = resolve_transcriber(include_xai=True)
    assert isinstance(transcriber, XaiSttTranscriber)


def test_resolve_transcriber_returns_none_with_include_xai_when_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``include_xai=True`` still respects the missing-key gate.

    Without a configured ``XAI_API_KEY`` the gateway can't transcribe,
    so the caller must fall back to the metadata-only annotation
    rather than build a transcriber that will 401 on every call.
    """
    monkeypatch.setattr(settings, "voice_provider", "xai")
    monkeypatch.setattr(settings, "xai_api_key", "")
    assert resolve_transcriber(include_xai=True) is None


def test_resolve_transcriber_ignores_include_xai_for_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag is meaningless when another backend is configured.

    ``mistral`` / ``openai`` / ``local`` have always returned through
    ``resolve_transcriber``; ``include_xai`` only flips the xAI default.
    """
    monkeypatch.setattr(settings, "voice_provider", "mistral")
    monkeypatch.setattr(settings, "voice_mistral_api_key", "")
    assert resolve_transcriber() is None
    assert resolve_transcriber(include_xai=True) is None

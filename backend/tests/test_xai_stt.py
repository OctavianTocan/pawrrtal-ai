"""Tests for xAI STT helper used by Telegram voice notes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from app.infrastructure.config import settings
from app.providers.xai.stt import transcribe_xai_stt

pytestmark = pytest.mark.anyio


async def test_transcribe_xai_stt_uses_workspace_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """STT uses the normal XAI_API_KEY path, not xAI OAuth credentials."""
    monkeypatch.setattr("app.providers.xai.stt.resolve_api_key", lambda *_args: "workspace-key")
    monkeypatch.setattr(settings, "xai_api_key", "global-key")

    with respx.mock(base_url="https://api.x.ai") as router:
        route = router.post("/v1/stt").mock(
            return_value=httpx.Response(200, json={"text": "voice transcript"})
        )
        transcript = await transcribe_xai_stt(
            raw_bytes=b"OggS voice",
            file_name="voice.ogg",
            mime_type="audio/ogg",
            workspace_root=tmp_path,
        )

    assert transcript == "voice transcript"
    assert route.calls.last.request.headers["Authorization"] == "Bearer workspace-key"
    assert b'name="file"' in route.calls.last.request.content

"""xAI speech-to-text helper for Telegram voice notes.

Unlike the chat provider, STT intentionally uses the long-lived xAI API key
path only. The user-facing OAuth flow is for chat sessions; Telegram voice
notes are backend-side file uploads to xAI's REST STT endpoint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.infrastructure.config import settings
from app.infrastructure.keys import resolve_api_key

_DEFAULT_TIMEOUT_SECONDS = 90.0
_STT_URL = "https://api.x.ai/v1/stt"
_HTTP_CLIENT_ERROR = 400


class XaiSttError(RuntimeError):
    """Raised when xAI STT cannot produce a usable transcript."""


async def transcribe_xai_stt(
    *,
    raw_bytes: bytes,
    file_name: str,
    mime_type: str,
    workspace_root: Path | None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Transcribe an audio file through xAI's REST STT endpoint."""
    api_key = _resolve_stt_api_key(workspace_root)
    if not api_key:
        raise XaiSttError("xAI STT is not configured. Set XAI_API_KEY.")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            _STT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (file_name, raw_bytes, mime_type)},
        )
    if response.status_code >= _HTTP_CLIENT_ERROR:
        raise XaiSttError(f"xAI STT failed with HTTP {response.status_code}: {response.text}")

    payload = _json_object(response)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise XaiSttError("xAI STT returned an empty transcript.")
    return text


def _resolve_stt_api_key(workspace_root: Path | None) -> str | None:
    """Resolve the API-key-only credential for xAI STT."""
    if workspace_root is not None:
        workspace_key = resolve_api_key(workspace_root, "XAI_API_KEY")
        if workspace_key:
            return workspace_key
    return settings.xai_api_key or None


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Return a response JSON object or raise a clean STT error."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise XaiSttError("xAI STT returned non-JSON response.") from exc
    if not isinstance(payload, dict):
        raise XaiSttError("xAI STT returned a non-object response.")
    return payload

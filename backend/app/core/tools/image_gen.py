"""Core image-generation logic via the OpenAI Codex Responses backend.

This module handles the network call only.  The agent-loop adapter lives in
:mod:`app.core.tools.image_gen_agent`.

Auth path
---------
OpenAI Codex OAuth is used instead of a direct ``OPENAI_API_KEY``.  The
bearer token is resolved in the following order:

1. ``OPENAI_CODEX_OAUTH_TOKEN`` workspace / settings override.
2. The ``$CODEX_HOME/auth.json`` file written by ``@openai/codex`` (or
   OpenClaw's bundled Codex agent).  ``CODEX_HOME`` defaults to
   ``~/.codex`` when the env var is absent.

Wire shape
----------
Requests go to ``https://chatgpt.com/backend-api/codex/responses`` as a
streaming Responses API call with the built-in ``image_generation`` tool.
The generated image arrives as base64 in the ``response.completed`` SSE
event inside the output's ``image_generation_call`` item.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Responses-API endpoint that backs Codex OAuth image generation.
# The /codex sub-path is required — /backend-api/responses returns 403.
_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"

# The chat-completion model used by the Codex backend when the
# image_generation tool is invoked.  gpt-5.5 is current as of 2026-04.
_CODEX_BACKEND_MODEL = "gpt-5.5"

# Maximum wait for a complete streamed image response (seconds).
_DEFAULT_TIMEOUT_S = 180.0


def resolve_codex_oauth_token(override: str | None = None) -> str:
    """Return a usable Codex OAuth bearer token or raise ``RuntimeError``.

    Resolution order:
      1. ``override`` — caller-supplied value (e.g. from workspace env).
      2. ``$CODEX_HOME/auth.json`` — written by ``@openai/codex`` / OpenClaw.

    Args:
        override: Optional pre-resolved token string.

    Raises:
        RuntimeError: When no token can be located.
    """
    if override:
        return override

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    auth_file = codex_home / "auth.json"
    if auth_file.exists():
        try:
            data = json.loads(auth_file.read_text())
            token = data.get("tokens", {}).get("access_token", "")
            if isinstance(token, str) and token:
                logger.debug("image_gen: loaded Codex OAuth token from %s", auth_file)
                return token
        except Exception as exc:
            logger.warning("image_gen: failed to read %s: %s", auth_file, exc)

    raise RuntimeError(
        "No Codex OAuth token found. "
        "Either set OPENAI_CODEX_OAUTH_TOKEN in your workspace settings "
        "or sign in with the Codex CLI (`codex auth`)."
    )


def _find_image_b64(output: list[dict[str, Any]]) -> str | None:
    """Extract base64 PNG data from a Codex Responses output array."""
    for item in output:
        if item.get("type") == "image_generation_call":
            result = item.get("result")
            return result if isinstance(result, str) else None
    return None


async def _extract_b64_from_stream(response: httpx.Response) -> str | None:
    """Consume an SSE stream from the Codex backend and return the image b64."""
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            event = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "response.completed":
            continue
        output = event.get("response", {}).get("output", [])
        result = _find_image_b64(output)
        if result:
            return result
    return None


async def generate_image_via_codex(
    prompt: str,
    *,
    oauth_token: str,
    size: str = "1024x1024",
    quality: str = "medium",
) -> bytes:
    """Call the Codex Responses backend to generate an image.

    Uses the built-in ``image_generation`` tool in the Responses API.
    The request streams SSE; we consume the stream until a
    ``response.completed`` event carrying image data arrives.

    Args:
        prompt: Natural-language description of the desired image.
        oauth_token: Valid Codex OAuth bearer token.
        size: Image dimensions string (e.g. ``"1024x1024"``, ``"1024x1536"``).
        quality: Generation quality — ``"low"``, ``"medium"``, or ``"high"``.

    Returns:
        Raw PNG bytes of the generated image.

    Raises:
        httpx.HTTPStatusError: On non-2xx response from the Codex backend.
        ValueError: When the stream completes without yielding image data.
    """
    payload: dict[str, Any] = {
        "model": _CODEX_BACKEND_MODEL,
        "input": [{"role": "user", "content": prompt}],
        "tools": [
            {
                "type": "image_generation",
                "quality": quality,
                "size": size,
            }
        ],
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "openai-intent": "agentic",
    }

    logger.info(
        "image_gen: requesting %s %s quality=%s size=%s",
        _CODEX_RESPONSES_URL,
        _CODEX_BACKEND_MODEL,
        quality,
        size,
    )

    async with (
        httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_S) as client,
        client.stream(
            "POST",
            _CODEX_RESPONSES_URL,
            json=payload,
            headers=headers,
        ) as response,
    ):
        response.raise_for_status()

        image_b64 = await _extract_b64_from_stream(response)

    if not image_b64:
        raise ValueError(
            "Codex image generation stream ended without returning image data. "
            "The model may not have invoked the image_generation tool."
        )

    logger.info("image_gen: received %d base64 chars", len(image_b64))
    return base64.b64decode(image_b64)

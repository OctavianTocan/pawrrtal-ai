"""Speech-to-text proxy router.

Wraps xAI's HTTP STT endpoint so the API key never leaves the server. The
frontend records audio via the browser ``MediaRecorder`` API, POSTs the
resulting blob to ``POST /api/v1/stt``, and we forward it to
``https://api.x.ai/v1/stt`` with the configured ``XAI_API_KEY``.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keys import resolve_api_key
from app.crud.workspace import get_default_workspace
from app.db import User, get_async_session
from app.users import get_allowed_user

logger = logging.getLogger(__name__)

# xAI's documented STT endpoint. Kept module-level so callers / tests can
# monkey-patch it without poking at the function body.
XAI_STT_URL = "https://api.x.ai/v1/stt"

# Hard cap forwarded to xAI is 500 MB; cap our local pre-forward read at a
# more reasonable 25 MB so a runaway / unauth user can't exhaust memory.
MAX_AUDIO_BYTES = 25 * 1024 * 1024

# How long to wait on xAI before giving up. STT for a typical voice note
# completes in 1-3 s; 60 s is a generous ceiling for longer recordings.
STT_TIMEOUT_SECONDS = 60.0

# Boundary at which the upstream response is treated as an error and
# surfaced verbatim to the client. Mirrors HTTP semantics — any 4xx/5xx.
HTTP_ERROR_STATUS_FLOOR = 400


def get_stt_router() -> APIRouter:  # noqa: C901 — single cohesive STT route + dispatch shim
    """Build the STT proxy router."""
    router = APIRouter(prefix="/api/v1/stt", tags=["stt"])

    @router.post("")
    async def transcribe_audio(  # noqa: C901 — xAI legacy path + alt-backend dispatch live in one route
        file: UploadFile = File(...),
        language: str | None = Form(default=None),
        format: bool = Form(default=True),  # noqa: A002
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> JSONResponse:
        """Forward an uploaded audio file to xAI and return the transcript JSON.

        ``file`` must be the raw audio blob (the browser default
        ``audio/webm;codecs=opus`` is accepted as an Opus container by xAI).
        ``language`` (optional) enables xAI's text formatting when supplied
        alongside ``format=True`` — defaults to English.

        Returns the upstream JSON response unmodified so the frontend has
        access to ``text``, ``duration``, and the optional ``words`` array.
        """
        # PR 14: when the operator selected a non-xAI backend, dispatch
        # to the configured ``Transcriber`` (Mistral / OpenAI / local
        # whisper.cpp).  The xAI proxy below is the historical default
        # and stays the path when ``settings.voice_provider == "xai"``.
        from app.integrations.voice import (  # noqa: PLC0415 — local import keeps the route light when voice extras unused
            TranscriptionError,
            resolve_transcriber,
        )

        transcriber = resolve_transcriber()
        if transcriber is not None:
            audio_bytes_alt = await file.read(MAX_AUDIO_BYTES + 1)
            if len(audio_bytes_alt) > MAX_AUDIO_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Audio exceeds the {MAX_AUDIO_BYTES // (1024 * 1024)} MB upload cap.",
                )
            if not audio_bytes_alt:
                raise HTTPException(status_code=422, detail="Audio file is empty.")
            try:
                text = await transcriber.transcribe(audio_bytes_alt)
            except TranscriptionError as exc:
                logger.warning("VOICE_TRANSCRIBE_FAILED provider=%s", "alt", exc_info=exc)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return JSONResponse(content={"text": text})

        # STT runs against the user's default workspace's configured key —
        # there's no concept of "STT for workspace X" in the UI yet, so the
        # default is the only sensible choice.  `resolve_api_key` already
        # falls back to `settings.xai_api_key`, so the caller doesn't need a
        # manual `or settings.x` suffix.
        workspace = await get_default_workspace(user.id, session)
        api_key = resolve_api_key(workspace.id, "XAI_API_KEY") if workspace is not None else None
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Speech-to-text is not configured. Set XAI_API_KEY in the backend env.",
            )

        # Read the upload up to our cap. Using ``await file.read()`` rather
        # than streaming because xAI requires the file in a multipart body
        # — there's no benefit to chunked passthrough for the typical < 25 MB
        # voice note.
        audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio exceeds the {MAX_AUDIO_BYTES // (1024 * 1024)} MB upload cap.",
            )
        if not audio_bytes:
            raise HTTPException(status_code=422, detail="Audio file is empty.")

        # xAI's docs: the `file` field MUST be the last entry in the multipart
        # body. httpx preserves insertion order from the `data` + `files`
        # tuples below — language/format first, file last.
        upstream_data: dict[str, str] = {}
        if language:
            upstream_data["language"] = language
        if format:
            upstream_data["format"] = "true"

        upstream_files = {
            "file": (
                file.filename or "audio.webm",
                audio_bytes,
                file.content_type or "audio/webm",
            ),
        }

        try:
            async with httpx.AsyncClient(timeout=STT_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    XAI_STT_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=upstream_data,
                    files=upstream_files,
                )
        except httpx.TimeoutException as error:
            logger.warning("xAI STT timeout after %ss", STT_TIMEOUT_SECONDS, exc_info=error)
            raise HTTPException(status_code=504, detail="Transcription timed out.") from error
        except httpx.RequestError as error:
            logger.warning("xAI STT request failed: %s", error)
            raise HTTPException(
                status_code=502, detail="Transcription provider unreachable."
            ) from error

        if response.status_code >= HTTP_ERROR_STATUS_FLOOR:
            # Surface xAI's error body to the frontend so the user sees the
            # actual cause (e.g. unsupported format, rate limited) instead of
            # a generic 502.
            logger.warning(
                "xAI STT returned %s: %s",
                response.status_code,
                response.text[:500],
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text or "Transcription failed.",
            )

        return JSONResponse(content=response.json(), status_code=200)

    return router

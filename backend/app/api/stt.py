"""Speech-to-text proxy router.

Wraps the configured voice backend so API keys never leave the server.
The frontend records audio via the browser ``MediaRecorder`` API,
POSTs the resulting blob to ``POST /api/v1/stt``, and the route
dispatches to whichever :class:`Transcriber` matches
``settings.voice_provider``.

For ``voice_provider == "xai"`` the route resolves ``XAI_API_KEY``
from the user's default workspace first (per the OVERRIDABLE_KEYS
convention), falling back to the gateway global; for every other
backend the global ``resolve_transcriber()`` helper does the wiring.
The Telegram bot uses the same backends via the global helper — see
``app/integrations/voice/transcriber.py``.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.keys import resolve_api_key
from app.crud.workspace import get_default_workspace
from app.db import User, get_async_session
from app.users import get_allowed_user

if TYPE_CHECKING:
    from app.integrations.voice import Transcriber, XaiSttTranscriber

logger = logging.getLogger(__name__)

# Hard cap on the audio payload we accept before any backend call.
# xAI's documented cap is 500 MB; we cap our local pre-forward read at
# a more reasonable 25 MB so a runaway / unauth user can't exhaust
# memory.
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def get_stt_router() -> APIRouter:
    """Build the STT proxy router."""
    router = APIRouter(prefix="/api/v1/stt", tags=["stt"])

    @router.post("")
    async def transcribe_audio(
        file: UploadFile = File(...),
        language: str | None = Form(default=None),
        format: bool = Form(default=True),  # noqa: A002 — matches xAI's docs
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> JSONResponse:
        """Forward an uploaded audio file to the configured backend.

        ``file`` must be the raw audio blob (the browser default
        ``audio/webm;codecs=opus`` is accepted as an Opus container).
        ``language`` (optional) and ``format`` are honoured by the
        xAI backend; other backends ignore them.

        Returns ``{"text": "..."}`` regardless of which backend ran,
        matching the contract the frontend's ``use-voice-transcribe``
        hook expects.
        """
        from app.integrations.voice import (  # noqa: PLC0415 — optional dep
            TranscriptionError,
            XaiSttTranscriber,
            resolve_transcriber,
        )

        audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio exceeds the {MAX_AUDIO_BYTES // (1024 * 1024)} MB upload cap.",
            )
        if not audio_bytes:
            raise HTTPException(status_code=422, detail="Audio file is empty.")

        transcriber = await _build_transcriber(
            user=user,
            session=session,
            language=language,
            request_format=format,
            resolve_global=resolve_transcriber,
            xai_factory=XaiSttTranscriber,
        )
        try:
            text = await transcriber.transcribe(audio_bytes)
        except TranscriptionError as exc:
            logger.warning("STT_BACKEND_FAIL provider=%s", settings.voice_provider, exc_info=exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(content={"text": text})

    return router


async def _build_transcriber(
    *,
    user: User,
    session: AsyncSession,
    language: str | None,
    request_format: bool,
    resolve_global: Callable[[], "Transcriber | None"],
    xai_factory: type["XaiSttTranscriber"],
) -> "Transcriber":
    """Pick the configured Transcriber, preferring workspace-scoped xAI keys.

    Web users can override ``XAI_API_KEY`` per-workspace via the
    encrypted ``.env``; the resolver-driven path in
    :mod:`app.integrations.voice.transcriber` only sees the global
    setting, so this branch does the workspace lookup explicitly and
    constructs the transcriber directly.  Non-xAI backends go through
    the global resolver — their config is already global.
    """
    if settings.voice_provider == "xai":
        workspace = await get_default_workspace(user.id, session)
        api_key = (
            resolve_api_key(Path(workspace.path), "XAI_API_KEY") if workspace is not None else None
        )
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Speech-to-text is not configured. Set XAI_API_KEY in the backend env.",
            )
        return xai_factory(api_key=api_key, language=language, format=request_format)

    built = resolve_global()
    if built is None:
        raise HTTPException(
            status_code=503,
            detail=(f"Speech-to-text is not configured for provider={settings.voice_provider!r}."),
        )
    return built

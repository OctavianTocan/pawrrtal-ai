"""Four voice-transcription backends behind a tiny Protocol.

Ported in shape from claude-code-telegram's ``voice_handler.py`` —
the API-key-bearing backends use lazy imports so a deployment that
sticks with xAI doesn't pay the install cost for ``mistralai`` /
``openai``; the local backend shells out to ``whisper.cpp`` via
ffmpeg; the xAI backend is a thin httpx wrapper around xAI's HTTP
STT endpoint, so non-Telegram surfaces (the web ``/api/v1/stt`` route)
and Telegram both go through the same code path now.

Each backend raises :class:`TranscriptionError` on failure with a
short human-readable reason; the route translates into HTTP 502
so the frontend can render a clean error toast.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# Subprocess timeout shared by ffmpeg + whisper.cpp.  Long voice notes
# can take a while to transcribe locally; 120s covers a 5-minute clip
# on a modest box.
_LOCAL_SUBPROCESS_TIMEOUT_S = 120

# Wall-clock cap for any single xAI HTTP STT call.  A typical voice
# note transcribes in 1-3 s; the long tail (multi-minute clips) still
# finishes well under a minute.  Kept the same as the previous
# inline-route default so we don't surprise existing operators.
_XAI_STT_TIMEOUT_S = 60.0

# xAI's documented STT endpoint.  Kept module-level so tests can
# monkey-patch without poking at the class body.
XAI_STT_URL = "https://api.x.ai/v1/stt"

# Status floor at which xAI's response is treated as an error.  Mirrors
# HTTP semantics — any 4xx / 5xx becomes a :class:`TranscriptionError`.
_HTTP_ERROR_STATUS_FLOOR = 400


class TranscriptionError(RuntimeError):
    """Raised by any backend when transcription fails."""


class Transcriber(Protocol):
    """Async transcription backend interface."""

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Return the plain-text transcription of ``audio_bytes``."""
        ...


class MistralVoxtralTranscriber:
    """Voxtral transcription via the Mistral SDK (lazy import)."""

    def __init__(self, api_key: str, model: str = "voxtral-mini-latest") -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Return the plain-text transcription of ``audio_bytes``."""
        client = self._get_client()
        try:
            response = await client.audio.transcriptions.complete_async(
                model=self._model,
                file={"content": audio_bytes, "file_name": "voice.ogg"},
            )
        except Exception as exc:
            logger.warning("MISTRAL_TRANSCRIBE_FAIL error_type=%s", type(exc).__name__)
            raise TranscriptionError("Mistral transcription request failed.") from exc
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise TranscriptionError("Mistral returned an empty transcription.")
        return text

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            # ``mistralai`` lives behind the optional ``[voice]`` extra,
            # so its stubs are not installed in the default environment.
            # The ModuleNotFoundError below is the load-bearing guard.
            from mistralai import Mistral  # type: ignore[import-not-found]  # noqa: PLC0415
        except ModuleNotFoundError as exc:
            raise TranscriptionError(
                "Optional dependency 'mistralai' is missing.  "
                'Install: pip install "pawrrtal-api[voice]"'
            ) from exc
        self._client = Mistral(api_key=self._api_key)
        return self._client


class OpenAIWhisperTranscriber:
    """Whisper transcription via the OpenAI SDK (lazy import)."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Return the plain-text transcription of ``audio_bytes``."""
        client = self._get_client()
        try:
            response = await client.audio.transcriptions.create(
                model=self._model,
                file=("voice.ogg", audio_bytes),
            )
        except Exception as exc:
            logger.warning("OPENAI_TRANSCRIBE_FAIL error_type=%s", type(exc).__name__)
            raise TranscriptionError("OpenAI transcription request failed.") from exc
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise TranscriptionError("OpenAI returned an empty transcription.")
        return text

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            # ``openai`` lives behind the optional ``[voice]`` extra,
            # so its stubs are not installed in the default environment.
            # The ModuleNotFoundError below is the load-bearing guard.
            from openai import AsyncOpenAI  # noqa: PLC0415
        except ModuleNotFoundError as exc:
            raise TranscriptionError(
                "Optional dependency 'openai' is missing.  "
                'Install: pip install "pawrrtal-api[voice]"'
            ) from exc
        self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client


class LocalWhisperCppTranscriber:
    """whisper.cpp via ffmpeg + subprocess; no Python dependency."""

    def __init__(self, binary_path: str | None, model_path: str) -> None:
        self._binary_path = binary_path
        self._model_path = model_path
        self._resolved_binary: str | None = None

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Return the plain-text transcription of ``audio_bytes``."""
        binary = self._resolve_binary()
        model = self._model_path
        # ASYNC240 disabled here — whisper.cpp model paths are local
        # filesystem checks resolved once per request (cheap stat),
        # not the kind of repeated I/O that ASYNC240 is guarding
        # against.  An anyio.Path round-trip would add overhead
        # without changing behaviour.
        if not Path(model).is_file():  # noqa: ASYNC240
            raise TranscriptionError(
                f"whisper.cpp model not found at '{model}'.  "
                "Download e.g. ggml-base.bin from huggingface.co/ggerganov/whisper.cpp."
            )
        tmp_dir = tempfile.mkdtemp(prefix="pawrrtal-voice-")
        try:
            ogg_path = Path(tmp_dir) / "voice.ogg"
            wav_path = Path(tmp_dir) / "voice.wav"
            ogg_path.write_bytes(audio_bytes)
            await self._convert_to_wav(ogg_path, wav_path)
            text = await self._run_whisper_cpp(binary, model, wav_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        text = text.strip()
        if not text:
            raise TranscriptionError("whisper.cpp returned an empty transcription.")
        return text

    def _resolve_binary(self) -> str:
        if self._resolved_binary is not None:
            return self._resolved_binary
        candidate = self._binary_path or "whisper-cli"
        resolved = shutil.which(candidate)
        if not resolved:
            raise TranscriptionError(
                f"whisper.cpp binary '{candidate}' not on PATH.  "
                "Set WHISPER_CPP_BINARY_PATH or install whisper.cpp."
            )
        self._resolved_binary = resolved
        return resolved

    @staticmethod
    async def _convert_to_wav(ogg_path: Path, wav_path: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            str(ogg_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            str(wav_path),
            "-y",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_LOCAL_SUBPROCESS_TIMEOUT_S
            )
        except TimeoutError as exc:
            proc.kill()
            raise TranscriptionError("ffmpeg timed out converting voice note.") from exc
        if proc.returncode != 0:
            raise TranscriptionError(f"ffmpeg exit {proc.returncode}: {stderr.decode()[:200]}")

    @staticmethod
    async def _run_whisper_cpp(binary: str, model: str, wav_path: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "-m",
            model,
            "-f",
            str(wav_path),
            "--no-timestamps",
            "-l",
            "auto",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_LOCAL_SUBPROCESS_TIMEOUT_S
            )
        except TimeoutError as exc:
            proc.kill()
            raise TranscriptionError("whisper.cpp timed out.") from exc
        if proc.returncode != 0:
            raise TranscriptionError(
                f"whisper.cpp exit {proc.returncode}; check binary + model path."
            )
        return stdout.decode()


class XaiSttTranscriber:
    """xAI HTTP STT endpoint, wrapped as a :class:`Transcriber`.

    Used by both the web ``/api/v1/stt`` route (with the workspace-
    resolved ``XAI_API_KEY``) and the Telegram bot (with the global
    ``settings.xai_api_key``).  Previously the route did its own
    inline ``httpx.AsyncClient.post(...)`` and the Telegram bot
    silently skipped — the Telegram skip was the reported bug.
    """

    def __init__(
        self,
        api_key: str,
        *,
        language: str | None = None,
        format: bool = True,  # noqa: A002 — matches xAI's docs + the route's form field
        timeout_seconds: float = _XAI_STT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._language = language
        self._format = format
        self._timeout_seconds = timeout_seconds

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Return the plain-text transcription of ``audio_bytes``."""
        # xAI's docs: the `file` field MUST be the last entry in the
        # multipart body.  httpx preserves insertion order from the
        # `data` + `files` tuples below.
        data: dict[str, str] = {}
        if self._language:
            data["language"] = self._language
        if self._format:
            data["format"] = "true"
        files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    XAI_STT_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data=data,
                    files=files,
                )
        except httpx.TimeoutException as exc:
            raise TranscriptionError(f"xAI STT timed out after {self._timeout_seconds}s.") from exc
        except httpx.RequestError as exc:
            logger.warning("XAI_STT_REQUEST_FAIL error=%s", exc)
            raise TranscriptionError("xAI STT request failed.") from exc

        if response.status_code >= _HTTP_ERROR_STATUS_FLOOR:
            # Surface xAI's error body so deployers see the actual
            # cause (rate limited, unsupported format, etc.).
            logger.warning("XAI_STT_HTTP_%s body=%s", response.status_code, response.text[:200])
            raise TranscriptionError(
                f"xAI STT returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise TranscriptionError("xAI STT returned a non-JSON body.") from exc
        text = (payload.get("text") if isinstance(payload, dict) else None) or ""
        text = text.strip()
        if not text:
            raise TranscriptionError("xAI returned an empty transcription.")
        return text


def resolve_transcriber() -> Transcriber | None:
    """Build the configured backend, or ``None`` when nothing is wired up.

    Returns a :class:`Transcriber` for every provider supported by
    ``settings.voice_provider``.  Callers — the web ``/api/v1/stt``
    route and the Telegram bot — invoke the result uniformly.  The
    xAI branch uses the global ``settings.xai_api_key``; surfaces that
    have a workspace context (the web route) and want workspace-first
    precedence should construct :class:`XaiSttTranscriber` directly
    with the workspace-resolved key instead of relying on this helper.
    """
    builder = _PROVIDER_BUILDERS.get(settings.voice_provider)
    if builder is None:
        return None
    return builder()


def _build_xai() -> Transcriber | None:
    if not settings.xai_api_key:
        return None
    return XaiSttTranscriber(api_key=settings.xai_api_key)


def _build_mistral() -> Transcriber | None:
    if not settings.voice_mistral_api_key:
        return None
    return MistralVoxtralTranscriber(api_key=settings.voice_mistral_api_key)


def _build_openai() -> Transcriber | None:
    if not settings.voice_openai_api_key:
        return None
    return OpenAIWhisperTranscriber(api_key=settings.voice_openai_api_key)


def _build_local() -> Transcriber | None:
    return LocalWhisperCppTranscriber(
        binary_path=settings.voice_whisper_cpp_binary or None,
        model_path=settings.voice_whisper_cpp_model,
    )


# Provider-name → builder function.  The dict form keeps the branch
# count under ruff's PLR0911 ceiling (max 6 returns per function) and
# makes a new backend a one-line addition.
_PROVIDER_BUILDERS: dict[str, Callable[[], Transcriber | None]] = {
    "xai": _build_xai,
    "mistral": _build_mistral,
    "openai": _build_openai,
    "local": _build_local,
}

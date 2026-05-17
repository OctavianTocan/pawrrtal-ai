"""Three voice-transcription backends behind a tiny Protocol.

Ported in shape from claude-code-telegram's ``voice_handler.py`` —
the API-key-bearing backends use lazy imports so a deployment that
sticks with xAI doesn't pay the install cost for ``mistralai`` /
``openai``; the local backend shells out to ``whisper.cpp`` via
ffmpeg.

Each backend raises :class:`TranscriptionError` on failure with a
short human-readable reason; the route translates into HTTP 502
so the frontend can render a clean error toast.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


# Subprocess timeout shared by ffmpeg + whisper.cpp.  Long voice notes
# can take a while to transcribe locally; 120s covers a 5-minute clip
# on a modest box.
_LOCAL_SUBPROCESS_TIMEOUT_S = 120


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
            from openai import AsyncOpenAI  # type: ignore[import-not-found]  # noqa: PLC0415
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


def resolve_transcriber() -> Transcriber | None:
    """Build the configured backend.  Returns ``None`` for ``xai`` (legacy path).

    The xAI proxy lives in ``api/stt.py`` and is the historical path.
    The other three backends are returned as :class:`Transcriber`
    instances the route can call uniformly.
    """
    provider = settings.voice_provider
    if provider == "mistral":
        if not settings.voice_mistral_api_key:
            return None
        return MistralVoxtralTranscriber(api_key=settings.voice_mistral_api_key)
    if provider == "openai":
        if not settings.voice_openai_api_key:
            return None
        return OpenAIWhisperTranscriber(api_key=settings.voice_openai_api_key)
    if provider == "local":
        return LocalWhisperCppTranscriber(
            binary_path=settings.voice_whisper_cpp_binary or None,
            model_path=settings.voice_whisper_cpp_model,
        )
    return None

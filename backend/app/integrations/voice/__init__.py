"""Pluggable voice-transcription backends.

Selected by ``settings.voice_provider`` — one of:

* ``xai`` (default; uses :class:`XaiSttTranscriber` against
  ``https://api.x.ai/v1/stt``)
* ``mistral`` (Voxtral)
* ``openai`` (Whisper)
* ``local`` (whisper.cpp via ffmpeg subprocess)

All four backends share the :class:`Transcriber` Protocol so the
``api/stt.py`` route, the Telegram bot, and any future surface can
dispatch on ``settings.voice_provider`` without knowing which backend
is wired up.
"""

from app.integrations.voice.transcriber import (
    LocalWhisperCppTranscriber,
    MistralVoxtralTranscriber,
    OpenAIWhisperTranscriber,
    Transcriber,
    TranscriptionError,
    XaiSttTranscriber,
    resolve_transcriber,
)

__all__ = [
    "LocalWhisperCppTranscriber",
    "MistralVoxtralTranscriber",
    "OpenAIWhisperTranscriber",
    "Transcriber",
    "TranscriptionError",
    "XaiSttTranscriber",
    "resolve_transcriber",
]

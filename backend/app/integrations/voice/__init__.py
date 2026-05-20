"""Pluggable voice-transcription backends.

Selected by ``settings.voice_provider`` — one of:

* ``xai`` (default; HTTP STT endpoint shared with ``api/stt.py``)
* ``mistral`` (Voxtral)
* ``openai`` (Whisper)
* ``local`` (whisper.cpp via ffmpeg subprocess)

All four backends share the :class:`Transcriber` Protocol so both
``api/stt.py`` (web composer) and Telegram voice ingestion can
dispatch uniformly without knowing which backend is wired up (#374).
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

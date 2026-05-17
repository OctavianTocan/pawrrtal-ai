---
# pawrrtal-0rah
title: Phase 6 — make_telegram_sender (MIME-routed send_message wiring)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:13Z
updated_at: 2026-05-14T19:52:13Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-ro2q
---

## Why

The agent can call a `send_message` tool to push artifacts (images, audio,
documents) to the user mid-turn. The tool itself is **channel-agnostic** —
it lives in `backend/app/core/tools/send_message.py` (preserved, not deleted)
and takes a `SendFn` callback.

`make_telegram_sender` is the factory that returns a Telegram-specific
`SendFn`. It picks the right aiogram method based on detected MIME and
threads the optional `message_thread_id` through every call so media lands
in the correct forum topic.

The LLM never knows what channel it's in. It produces a file path + MIME and
the channel decides "this is an image → sendPhoto" or "this is OGG → sendVoice
so Telegram renders it as a voice note in-chat".

## What to build

Add to the same file as `TelegramChannel`: `backend/app/channels/telegram.py`.

```
from app.core.tools.send_message import SendFn
```

`SendFn` is `Callable[[str | None, Path | None, str | None], Awaitable[None]]`
— it takes `(text, file_path, mime)` and returns nothing.

### `make_telegram_sender(bot, chat_id, *, message_thread_id=None) -> SendFn`

Pseudocode:

```
def make_telegram_sender(bot, chat_id, *, message_thread_id=None):
    async def _send(text, file_path, mime):
        thread_kwargs <- {"message_thread_id": message_thread_id} if message_thread_id is not None else {}

        if file_path is None:
            # Text-only
            await bot.send_message(chat_id=chat_id, text=text or "", **thread_kwargs)
            return

        # Lazy import — aiogram is optional dep
        from aiogram.types import FSInputFile
        file    <- FSInputFile(file_path)
        caption <- text or None     # NOT ""; aiogram dislikes empty captions on some methods
        m       <- (mime or "").lower()

        # MIME routing — order matters: more specific before more general
        if m.startswith("image/"):
            await bot.send_photo(chat_id, photo=file, caption=caption, **thread_kwargs); return

        if m in ("audio/ogg", "audio/opus"):
            # Telegram renders OGG/Opus as an in-chat voice note (not a download)
            await bot.send_voice(chat_id, voice=file, caption=caption, **thread_kwargs); return

        if m.startswith("audio/"):
            await bot.send_audio(chat_id, audio=file, caption=caption, **thread_kwargs); return

        if m.startswith("video/"):
            await bot.send_video(chat_id, video=file, caption=caption, **thread_kwargs); return

        # Fallback: anything else lands as a downloadable document
        await bot.send_document(chat_id, document=file, caption=caption, **thread_kwargs)

    return _send
```

## Why the OGG/Opus special case

Telegram has two ways to send audio:
- `sendAudio` → renders as a track in a music player UI; user has to tap play
- `sendVoice` → renders inline as a waveform voice note, autoplay-ready

OGG/Opus is the codec Telegram itself uses for voice notes. If your agent
emits a `.ogg`, the user wants the voice note UX — not a tracks-list entry.
Any other audio codec falls through to `sendAudio`.

## Why lazy import of `FSInputFile`

`aiogram` is an optional dependency in some deployments (the channel-agnostic
core needs to load even when aiogram isn't installed). The function-local
import means the cost is paid only when someone actually attaches a file via
this Telegram sender.

## Why `caption = text or None` (not `text or ""`)

aiogram passes `caption=""` to Telegram which then renders an empty caption
strip under the media. Passing `None` omits the parameter entirely. The
agent should be able to send a bare image with no caption.

## Why `thread_kwargs` instead of always passing `message_thread_id`

`message_thread_id=None` is **not** the same as omitting the parameter to
aiogram — passing `None` makes the API call without thread routing, but
some aiogram versions / chat types reject `None` explicitly. The
`**thread_kwargs` pattern only forwards the kwarg when it's set, so DMs
without topics never see the parameter at all.

## Edge cases

- The `SendFn` signature **does not raise** on transport errors directly —
  the tool itself catches and returns a JSON error string. But if aiogram
  raises `TelegramBadRequest`, it propagates up. Tests assert that the tool
  catches it and renders an error.
- `file_path` is a fully resolved absolute `Path` by the time it reaches
  this function — the tool body validated it against the workspace root.
  Don't re-validate here.
- MIME detection is the tool's job (it calls `mimetypes.guess_type`). The
  sender treats `mime=None` as "send as document".
- `chat_id` may be `str` or `int` (Telegram supports either). Pass through.

## Tests that should pass after this

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_send_message_tool.py::TestMakeTelegramSender \
  -x
```

All 11 routing tests should go green (image, ogg, opus, mp3, video, pdf,
unknown, text-only, thread_id-included, thread_id-absent, caption variants).

The `TestSendMessageTool` and `TestResolveAttachment` / `TestDetectMime`
classes test the channel-agnostic tool body which is **already in place**
under `backend/app/core/tools/send_message.py`. They should already pass.

## Next

Bean 7 — register `TelegramChannel` in the channel registry so
`resolve_channel("telegram")` returns it.

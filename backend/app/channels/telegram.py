"""TelegramChannel — progressive message-edit delivery via aiogram.

REBUILD STUB — beans ``pawrrtal-ro2q`` (Phase 5, the channel) and
``pawrrtal-0rah`` (Phase 6, the media sender factory).

SSE pushes bytes to an HTTP transport. Telegram doesn't — it edits a
placeholder message in-place. The Channel protocol returns
``AsyncIterator[bytes]``; Telegram has nothing to yield, but the type
signature still has to hold.
"""

# TODO(pawrrtal-ro2q): Telegram has a flood-control limit on edits per
#   chat per minute. A fast-emitting model would blow through it. The
#   channel needs to debounce — and the right debounce has TWO axes,
#   not one. Think about which axis fails on each end (slow tokens,
#   fast tokens).

# TODO(pawrrtal-ro2q): there's a hard message-length ceiling. Pick a
#   strategy: truncate, split, or refuse. Splitting is harder than it
#   looks (the placeholder is one message_id; edit_message_text can't
#   target a different message).

# TODO(pawrrtal-ro2q): one error from Telegram is benign and should be
#   swallowed. Any others should be logged but NOT re-raised — partial
#   delivery beats a crashed stream.

# TODO(pawrrtal-ro2q): cancellation has to propagate. The /stop command
#   cancels the asyncio task; the channel's loop must not swallow it.

# TODO(pawrrtal-ro2q): the deliver method's body is structurally an
#   async generator that yields nothing. Make sure it still IS one —
#   the type signature is AsyncIterator[bytes].

# TODO(pawrrtal-ro2q): the final flush is non-obvious. What does the
#   user see if you only flush at the debounce points?

# TODO(pawrrtal-0rah): the send_message tool calls a SendFn the channel
#   provides. Telegram's SendFn picks the API method by MIME. Some
#   MIMEs have a special in-Telegram rendering that affects the UX
#   (in-chat voice note vs music-player track). Others all collapse to
#   one fallback.

# TODO(pawrrtal-0rah): "no caption" and "empty caption" render
#   differently in Telegram. Don't pass an empty string when you mean
#   nothing.

# TODO(pawrrtal-0rah): forum topics — the optional thread_id param.
#   Passing None is not always equivalent to omitting the kwarg. Forward
#   it conditionally.

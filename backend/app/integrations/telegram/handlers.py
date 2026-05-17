"""Inbound message handlers for the Telegram channel adapter.

REBUILD STUB — bean ``pawrrtal-w8xp`` (Phase 8) has the full spec.

The design rule: **no aiogram imports in this file**. Handlers take a
plain dataclass and a session, return either a reply string or a turn
context. That's what makes the tests easy.
"""

# TODO(pawrrtal-w8xp): two frozen dataclasses live in this file. One
#   represents an inbound sender (the framework-thin shape of an aiogram
#   Message.from_user). One represents the resolved turn context the
#   dispatcher hands to the LLM pipeline.

# TODO(pawrrtal-w8xp): handlers can return either a string or a turn
#   context. The dispatcher branches on isinstance. Why both? Because
#   some replies are terminal (unbound user nudge, code-redemption
#   confirmation, command outputs) and some are "now route to the LLM".

# TODO(pawrrtal-w8xp): the "user isn't bound yet" nudge tells them to
#   send the code. So a plain message that happens to LOOK like a code
#   should be auto-redeemed too — but only when it matches the exact
#   shape, not arbitrary chatter.

# TODO(pawrrtal-w8xp): /new always creates a fresh conversation row.
#   It is NOT a get-or-create — that's a different helper. Preserve
#   the thread_id so the new conversation stays in the same Telegram
#   topic.

# TODO(pawrrtal-w8xp): /stop's handler is synchronous. The actual
#   asyncio.Task cancellation lives in the dispatcher (Phase 11) which
#   owns the per-chat task dict. This handler just picks the right
#   reply string.

# TODO(pawrrtal-w8xp): /model parses but does NOT validate against the
#   catalog. An unknown-but-parseable ID gets stored and then caught by
#   the auto-clear safety net on the NEXT turn (Phase 11). That's an
#   intentional trade-off — see ADR 2026-05-14 §7.

# TODO(pawrrtal-w8xp): all reply copy at module scope. Bot uses HTML
#   parse mode, so literal angle brackets in copy must be entity-escaped.

# TODO(pawrrtal-w8xp): never log the plaintext code on a successful
#   bind — only the binding's user_id and the external_user_id.

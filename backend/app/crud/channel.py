"""Service helpers for the third-party messaging channel binding flow.

REBUILD STUB — bean ``pawrrtal-ei4l`` (Phase 3) has the full spec.

Two responsibilities once rebuilt: (1) the short-lived one-time code
handshake; (2) the persistent identity map plus the conversation routing
the bot reads on every inbound message.
"""

# TODO(pawrrtal-ei4l): codes are short and from a small alphabet — short
#   enough to type, small enough to brute-force offline if you store
#   them naively. Pick the storage primitive that defeats offline
#   grinding even with a leaked DB.

# TODO(pawrrtal-ei4l): the code alphabet matters. Think about what
#   happens at a support ticket when someone insists they typed it
#   correctly.

# TODO(pawrrtal-ei4l): redemption has multiple failure modes (missing,
#   expired, already used, wrong provider). The bot sees all of them
#   as the same reply. Why?

# TODO(pawrrtal-ei4l): what happens if a user unbinds and rebinds the
#   same Telegram account? Two rows in the bindings table would race for
#   "which Nexus user is this Telegram user?". Plan the merge path.

# TODO(pawrrtal-ei4l): the get-or-create for the Telegram conversation
#   has two branches — Telegram forum topics get their own row per
#   thread, plain DMs reuse one row. The "find existing" query for DMs
#   is non-obvious once the auto-title bean overwrites the title.

# TODO(pawrrtal-ei4l): one of the helpers is hit on every inbound
#   message — it should be a single indexed lookup, not a row fetch.

# TODO(pawrrtal-ei4l): there's a helper for clearing the per-conversation
#   model override. The auto-clear safety net in Phase 11 needs it; the
#   /model handler needs to set it. Same signature, both directions.

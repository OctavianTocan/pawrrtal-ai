"""HTTP endpoints for the third-party messaging channel binding flow.

REBUILD STUB — bean ``pawrrtal-1irw`` (Phase 4) has the full spec.

The frontend depends on the response shapes here. Don't ship from
imagination; look at what ``frontend/lib/channels.ts`` reads.
"""

# TODO(pawrrtal-1irw): two response schemas live in `app/schemas.py`,
#   not here. Re-add them there alongside this file's rebuild.

# TODO(pawrrtal-1irw): four routes total. Three the frontend hits, one
#   that only Telegram hits. The Telegram-only one should NOT be in
#   the OpenAPI schema.

# TODO(pawrrtal-1irw): the "channel not configured" branch is a real
#   user-facing state — the frontend has UI for it. Pick a status code
#   the hook can pattern-match on.

# TODO(pawrrtal-1irw): the webhook route has TWO independent guards
#   before it processes the body. What's the failure mode if you only
#   write one? (Hint: even with a perfect secret check, a polling
#   deployment shouldn't accept webhooks.)

# TODO(pawrrtal-1irw): unlinking is idempotent. The frontend doesn't
#   precheck state before hitting Disconnect. Status code should reflect
#   that.

# TODO(pawrrtal-1irw): after rebuilding, re-register in `backend/main.py`
#   — the deletion left a comment marker. Add the import too.

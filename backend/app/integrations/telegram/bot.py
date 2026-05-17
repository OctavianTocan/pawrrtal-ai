"""aiogram-backed Telegram bot service.

REBUILD STUB — bean ``pawrrtal-obsd`` (Phase 11) has the full spec.
Phase 10 (``pawrrtal-0v4v``) also lives here: the auto-title helpers
sit at module scope, not inside the dispatcher closure.

Thin glue between aiogram and the framework-free handlers. Two boot
modes (polling for laptops, webhook for prod) share the same handlers.
"""

# TODO(pawrrtal-obsd): in-flight stream tracking is a module-level dict
#   keyed by chat_id. It exists so /stop can cancel and so a new
#   message can cancel-then-replace the in-flight task. This is
#   PROCESS-LOCAL — single-worker only. Document it; the day someone
#   scales horizontally, this becomes Redis.

# TODO(pawrrtal-obsd): the lifespan has THREE no-op exit paths before
#   it tries to build a service. Order matters — demo mode wins over
#   token presence (a demo deploy may have a real token sitting in env).

# TODO(pawrrtal-obsd): polling mode has a footgun. If Telegram thinks
#   the bot is on webhook, getUpdates returns nothing. Always clear the
#   webhook at boot — and clear the queue while you're there.

# TODO(pawrrtal-obsd): aiogram's polling loop wants to install its own
#   signal handlers. uvicorn already owns those. Disable aiogram's.

# TODO(pawrrtal-obsd): five dispatcher routes. Order matters when
#   filters could overlap — CommandStart before generic message().

# TODO(pawrrtal-obsd): the run-LLM-turn coordinator does a few things in
#   order: send placeholder, load workspace + tools, resolve provider
#   with the auto-clear safety net, cancel any prior task for this chat,
#   start the new one, await, fire-and-forget auto-title. Each step is
#   small; the orchestration is what's tricky.

# TODO(pawrrtal-obsd): the auto-clear safety net. A stored model_id can
#   be parseable-but-unknown (because /model didn't catalog-check). On
#   chat time, catch the catalog miss, clear the override (NULL), fall
#   back to the catalog default for THIS turn, and tell the user what
#   happened.

# TODO(pawrrtal-obsd): _sender_from_message has to handle from_user=None
#   (anonymous channel posts). Reject — we don't process those.

# TODO(pawrrtal-obsd): the start-command payload is the deep-link
#   argument. aiogram exposes it on CommandObject, but reading from
#   message.text is robust to a user manually typing `/start ABC123`.

# TODO(pawrrtal-0v4v): the auto-title helper has a fire-once gate. The
#   gate is a marker column on the conversation, NOT title-content
#   inspection. Three states: never run, ran (auto), user-edited.

# TODO(pawrrtal-0v4v): if the conversation is in a Telegram forum
#   topic, the helper also renames the topic via editForumTopic so the
#   user's Topics list matches. That call has many failure modes
#   (admin rights, supergroup state, rate limit). Failures must NOT
#   break the conversation — swallow and log.

# TODO(pawrrtal-0v4v): title generation strips a leading slash-command
#   in case the user's first message is "/new tell me about X". The
#   derived title should be "tell me about X", not "/new".

# TODO(pawrrtal-obsd): after rebuilding, re-export in this package's
#   __init__.py, then re-add the imports + lifespan + router in
#   `backend/main.py` (the deletion left comment markers).

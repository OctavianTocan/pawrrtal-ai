---
# pawrrtal-ei4l
title: Phase 3 — Channel CRUD helpers (HMAC link codes, bindings, conversation routing)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:12Z
updated_at: 2026-05-14T19:52:12Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-j8o1
---

## Why

This bean is the **auth handshake** + **conversation routing**. The HTTP API
and the bot dispatcher both call into here — the API to issue codes and list
bindings, the bot to redeem codes and resolve "Telegram user X is Nexus user
Y" on every inbound message.

Stakes: get the HMAC wrong and a leaked DB lets an attacker grind codes
offline. Get the topic-vs-DM branch wrong and `/new` in a topic creates a
conversation that bleeds into other topics.

## What to build

File: `backend/app/crud/channel.py`. Module-level constants + 8 async helpers.

### Module constants

```
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 32 chars, no look-alikes
_CODE_LENGTH = 8                                      # ~40 bits entropy
LINK_CODE_TTL = timedelta(minutes=10)                 # short on purpose
```

The alphabet excludes `0/O/1/I/L` so support tickets can't argue about what
the user typed. 8 × 32 ≈ 40 bits — fine for 10-minute single-use codes.

### Helpers (private)

```
def _utcnow() -> datetime:
    # naive UTC to match the other DateTime columns in this codebase
    return datetime.now(UTC).replace(tzinfo=None)

def _hash_code(code: str) -> str:
    # HMAC-SHA-256 keyed with settings.auth_secret, hex-encoded
    key = (settings.auth_secret or "").encode("utf-8")
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()

def _generate_code() -> str:
    # secrets.choice (not random.choice — cryptographic)
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
```

**Why HMAC, not bare SHA**: bare SHA of a known 32^8 alphabet is grindable in
seconds. HMAC with the server secret means the attacker also needs the key.

### Public helpers

#### `issue_link_code(user_id, provider, session) -> tuple[str, datetime]`

Pseudocode:

```
code      <- _generate_code()
code_hash <- _hash_code(code)
now       <- _utcnow()
expires   <- now + LINK_CODE_TTL
row       <- ChannelLinkCode(code_hash, user_id, provider,
                             created_at=now, expires_at=expires,
                             used_at=None)
session.add(row); await session.commit()
return (code, expires)        # plaintext returned ONCE, here
```

The plaintext leaves this function exactly once — for the HTTP response. It
never hits the DB.

#### `redeem_link_code(code, provider, external_user_id, external_chat_id, display_handle, session) -> ChannelBinding | None`

This is the bind handshake. Returns `None` for **any** failure mode (the bot
adapter shows a generic "code didn't work" — never leak which case it was).

Pseudocode:

```
code_hash <- _hash_code(code)
row       <- session.get(ChannelLinkCode, code_hash)
if row is None:                  return None
if row.provider != provider:     return None    # cross-provider replay
if row.used_at is not None:      return None
if row.expires_at <= _utcnow():  return None

# Re-bind path: same (provider, external_user_id) already exists?
existing <- SELECT FROM channel_bindings
              WHERE provider=? AND external_user_id=?
if existing is not None:
    existing.user_id          <- row.user_id
    existing.external_chat_id <- external_chat_id
    existing.display_handle   <- display_handle
    binding <- existing
else:
    binding <- ChannelBinding(user_id=row.user_id, provider, external_user_id,
                              external_chat_id, display_handle, created_at=now)
    session.add(binding)

row.used_at <- now
await session.commit()
await session.refresh(binding)
return binding
```

**Why the cross-provider guard**: a Telegram user must never be able to redeem
a Slack code (or vice versa). Different surface, different trust boundary.

**Why upsert on `(provider, external_user_id)`**: a user might unbind and
rebind. Two rows for the same identity would race for which binding wins.

#### `list_bindings(user_id, session) -> list[ChannelBinding]`

```
SELECT * FROM channel_bindings WHERE user_id=?
```

#### `delete_binding(user_id, provider, session) -> bool`

```
row <- SELECT * FROM channel_bindings WHERE user_id=? AND provider=?
if row is None: return False
await session.delete(row); await session.commit()
return True
```

Caller (`DELETE /api/v1/channels/telegram/link`) returns 204 either way for
idempotency, but the bool is useful for analytics.

#### `get_user_id_for_external(provider, external_user_id, session) -> uuid.UUID | None`

```
SELECT user_id FROM channel_bindings WHERE provider=? AND external_user_id=?
```

This is hit **on every inbound Telegram message**. Keep it a single index
lookup — don't fetch the whole row.

#### `get_or_create_telegram_conversation_full(user_id, session, thread_id=None) -> Conversation`

The DM-vs-topic branch:

```
if thread_id is not None:
    # Topic mode: each forum thread is its own conversation
    stmt <- SELECT * FROM conversations
              WHERE user_id=? AND telegram_thread_id=?
              ORDER BY created_at DESC LIMIT 1
else:
    # Legacy DM mode: reuse the most recent "Telegram*" conversation
    # that does NOT have a thread_id
    stmt <- SELECT * FROM conversations
              WHERE user_id=?
                AND title LIKE 'Telegram%'
                AND telegram_thread_id IS NULL
              ORDER BY updated_at DESC LIMIT 1

existing <- await session.execute(stmt).scalar_one_or_none()
if existing is not None: return existing

# No prior conversation — create one
conv <- Conversation(id=uuid4(), user_id, title="Telegram",
                      origin_channel="telegram",
                      telegram_thread_id=thread_id,
                      created_at=now, updated_at=now)
session.add(conv); await session.commit(); await session.refresh(conv)
return conv
```

**Why `title.like("Telegram%")` for DMs**: the auto-title bean overwrites
`title` with the derived first-message string, so you can't query by exact
match. The prefix-match is the legacy DM finder — once auto-title runs the
conversation is found by `updated_at DESC` LIMIT 1 instead.

`get_or_create_telegram_conversation(user_id, session) -> uuid.UUID` is a
convenience wrapper that returns just `conv.id` for callers that don't need
the full row. Optional — only add if tests demand it.

#### `update_conversation_model(conversation_id, model_id, session) -> bool`

```
row <- session.get(Conversation, conversation_id)
if row is None: return False
row.model_id <- model_id           # may be None to clear
await session.commit()
return True
```

Called by:
- `/model` handler (sets a canonical `host:vendor/model` string)
- The auto-clear safety net (sets `None` after a bad stored ID)

## Edge cases

- **Stolen-DB threat model**: HMAC means the attacker needs `settings.auth_secret`
  to grind codes. Keep that secret out of logs.
- **Code shape**: case-sensitive uppercase. The handler in bean 8 will upper
  the input before redeeming so a user typing lowercase still works.
- **Re-binding behavior**: a user who unbinds and rebinds gets the same
  `ChannelBinding.id` (the upsert path updates `user_id`/`chat_id`/`handle`
  in place). Don't try to be clever and `delete + create` — that orphans the
  `active_conversation_id` FK.
- **`title.like("Telegram%")`** is a starts-with query, not LIKE-anywhere.
  Use SQLAlchemy's `Conversation.title.like("Telegram%")` (the `%` is the
  trailing wildcard).
- **`ORDER BY updated_at DESC`** for DM lookup is important: once the
  Conversation has had a turn, `updated_at` bumps and the same row keeps
  winning the "most recent" query.

## Tests that should pass after this

Still none green directly (the HTTP layer in bean 4 is what tests target),
but smoke check the CRUD shape:

```bash
cd backend && .venv/bin/python -c "
from app.crud.channel import issue_link_code, redeem_link_code, list_bindings, \
  delete_binding, get_user_id_for_external, \
  get_or_create_telegram_conversation_full, update_conversation_model
print('imports OK')
"
```

## Next

Bean 4 — wrap this CRUD with HTTP routes at `/api/v1/channels`. After bean 4,
`test_channels_api.py` will start going green.

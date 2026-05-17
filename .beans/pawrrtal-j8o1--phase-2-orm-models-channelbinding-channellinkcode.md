---
# pawrrtal-j8o1
title: Phase 2 — ORM models (ChannelBinding, ChannelLinkCode, Conversation columns)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:12Z
updated_at: 2026-05-14T19:52:12Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-tfxd
---

## Why

The migrations created the tables; the ORM bindings are gone. Without them
SQLAlchemy can't query/insert and every CRUD function in the next bean is
unimportable.

Migrations to read for the canonical column types:

- `backend/alembic/versions/007_add_channel_bindings_and_link_codes.py`
- `backend/alembic/versions/011_add_channel_columns_and_attachment.py`

The DB already has every column you're about to declare. You're just
re-declaring the Python view.

## What to build

File: `backend/app/models.py` — add two classes and three columns on
`Conversation`.

### `ChannelBinding`

The persistent map from a third-party identity to a Nexus user. One row per
`(provider, external_user_id)` — enforced by a unique constraint named
`uq_channel_bindings_provider_external_user` (migration 007). Provider is
open-ended (`telegram`, `slack`, `whatsapp`); today only Telegram is wired.

Columns:

| Column | Type | Notes |
|---|---|---|
| `id` | `Uuid` PK | `default=uuid.uuid4` |
| `user_id` | `Uuid` FK `user.id` ON DELETE CASCADE | indexed |
| `provider` | `String(32)` | |
| `external_user_id` | `String(128)` | Telegram int coerced to text; opaque to us |
| `external_chat_id` | `String(128)` nullable | DM chat to push to; equals `external_user_id` for DMs |
| `display_handle` | `String(255)` nullable | Captured at bind time, **never used for auth** |
| `active_conversation_id` | `Uuid` FK `conversations.id` ON DELETE SET NULL | nullable; the live DM conversation |
| `has_topics_enabled` | `Boolean` | `default=False, server_default="false"` |
| `created_at` | `DateTime` | |

Table name: `channel_bindings`.

### `ChannelLinkCode`

The short-lived handshake row. Web app issues a code, user pastes it (or hits
the deep link), bot consumes the row to create a `ChannelBinding`. **The
plaintext is never stored** — only its HMAC. Lookups by `code_hash` so it's
the primary key.

Columns:

| Column | Type | Notes |
|---|---|---|
| `code_hash` | `String(128)` PK | HMAC-SHA-256 hex |
| `user_id` | `Uuid` FK `user.id` ON DELETE CASCADE | indexed |
| `provider` | `String(32)` | |
| `created_at` | `DateTime` | |
| `expires_at` | `DateTime` | indexed |
| `used_at` | `DateTime` nullable | NULL until consumed |

Table name: `channel_link_codes`.

### Conversation columns (re-add)

On the existing `Conversation` model, add **three** Mapped columns (already
present in DB via migration 011):

```
origin_channel: Mapped[str | None]      # String(32), nullable. e.g. "telegram", "web"
telegram_thread_id: Mapped[int | None]  # Integer, nullable. Bot API 9.3+ forum topic ID
title_set_by: Mapped[str | None]        # String(16), nullable. NULL | "auto" | "user"
```

`title_set_by` is the auto-title gate: NULL means "not yet titled", and the
auto-title helper only runs while it's NULL.

## Contracts

Don't change column types or names — the migrations are immutable history,
and your declarations have to match what's already in the DB. Use
`Mapped[T | None]` for nullable columns so type checkers cooperate.

`ChannelBinding.id` defaults to `uuid.uuid4`; `created_at` is set by the CRUD
layer, not at SQL default level (matches the convention used elsewhere in this
model file).

## Edge cases

- `external_user_id` is **text**, not an int. Telegram gives you ints, but
  Slack uses strings and WhatsApp uses phone numbers — keep the column shape
  stable across providers.
- `code_hash` is a hex string of fixed length (HMAC-SHA-256 → 64 hex chars).
  `String(128)` is roomy; do not shrink to `String(64)` — the CRUD helper in
  bean 3 uses `session.get(ChannelLinkCode, code_hash)` which means the
  string is the PK.
- `has_topics_enabled` has both `default=False` AND `server_default="false"`.
  The Python default keeps `add()`-without-explicit-value working; the SQL
  default keeps existing rows non-NULL after a column add.
- Do NOT add the `Conversation.model_id` column — it already exists from an
  earlier migration. Only the three columns listed above.

## Tests that should pass after this

```bash
cd backend && .venv/bin/python -m pytest tests/test_channels_api.py::test_list_channels_starts_empty -x
```

Will still fail with `ImportError` for the API module — that's fine, the
target is bean 4. But you've unblocked the imports that CRUD needs.

Smoke check that the ORM is wired:

```bash
cd backend && .venv/bin/python -c "
from app.models import ChannelBinding, ChannelLinkCode, Conversation
print(ChannelBinding.__tablename__, ChannelLinkCode.__tablename__)
print('origin_channel' in {c.name for c in Conversation.__table__.c})
"
```

## Next

Bean 3 — the CRUD layer (`backend/app/crud/channel.py`). HMAC link codes,
binding lookups, and the DM-vs-topic conversation routing logic.

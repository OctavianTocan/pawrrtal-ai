---
# pawrrtal-yogx
title: 'feat(paw): paw channels — Telegram link/unlink + simulate-update'
status: completed
type: feature
priority: low
created_at: 2026-05-27T20:08:17Z
updated_at: 2026-05-28T00:09:11Z
parent: pawrrtal-6cnv
---

v2 paw command. Telegram channel link/unlink + simulate-update for in-proc bot testing. See parent epic pawrrtal-6cnv and plan docs/superpowers/plans/2026-05-27-agent-cli-user.md (v2 deferred section).

## Summary of Changes

Shipped `paw channels` subcommand group covering the actual Telegram-binding HTTP surface in `backend/app/api/channels.py`:

- `paw channels list` (alias `ls`) — `GET /api/v1/channels`. Returns `ChannelBindingRead[]` (bare list). `--json` / `--plain` / human-table output.
- `paw channels link telegram` — `POST /api/v1/channels/telegram/link`. Issues a one-time code; the response carries `code`, `expires_at`, `bot_username`, `deep_link`. The CLI does NOT redeem codes — codes are pasted into the Telegram bot by the user. 503 (Telegram unconfigured) surfaces as ApiError exit 5.
- `paw channels unlink telegram` — `DELETE /api/v1/channels/telegram/link`. Idempotent 204 whether or not a binding existed. Requires `--yes`.

**Skipped: `simulate-update`.** No backend endpoint accepts synthetic Telegram updates today. The closest surface (`POST /api/v1/channels/telegram/webhook`) accepts only real Telegram payloads, requires the `X-Telegram-Bot-Api-Secret-Token` secret, and 404s outside webhook mode. Add `POST /api/v1/channels/{provider}/simulate` first; the verb can land alongside it without churning the rest of the CLI surface.

**Backend surprise reconciled:** the bean spec describes an ID-keyed surface (`unlink <id>`, `simulate-update <id>`). The actual backend is provider-keyed — `ChannelBindingRead` has no `id` field, just `(provider, external_user_id, display_handle, ...)`. The CLI now matches the backend: `unlink telegram`, not `unlink <id>`. When Slack/iMessage adapters land, they'll be sibling Typer subcommands (`paw channels link slack`, etc.).

**Files:**

- `backend/app/cli/paw/commands/channels.py` (new) — Typer app with three verbs + provider-namespaced subcommands for `link` / `unlink`.
- `backend/app/cli/paw/main.py` — register the channels Typer app.
- `backend/tests/paw/test_command_channels.py` (new) — 10 respx-mocked tests covering list (JSON / plain / empty / 401-auth-error), link telegram (success + 503-not-configured), unlink (requires `--yes` / 204 success / 500-api-error).
- `.claude/skills/paw/SKILL.md` — added the `channels` row to the Resource map; removed `paw channels` from the v2 deferred list.

**Verification:**

- `cd backend && uv run pytest -q tests/paw/test_command_channels.py` → 10 passed.
- `cd backend && uv run pytest -q tests/paw -x` → 116 passed (was 104 + 2 from concurrent work; +10 new).
- `cd backend && uv run ruff check app/cli/paw/commands/channels.py app/cli/paw/main.py tests/paw/test_command_channels.py` → clean.
- `cd backend && uv run mypy app/cli/paw/commands/channels.py` → clean.
- `cd backend && uv run paw channels --help` → renders four-row command table (list / ls / link / unlink).

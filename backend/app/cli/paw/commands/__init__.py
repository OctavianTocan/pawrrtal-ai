# <skill-gen>
# ---
# name: paw
# description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user -- auth, workspaces, chat with SSE streaming, conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
# ---
#
# ## Resource map
#
# Every row reflects a shipped subcommand. Treat `paw --help` and
# `backend/app/cli/paw/commands/` as authoritative when this map drifts.
#
# | Resource | Verbs | Endpoint family |
# | --- | --- | --- |
# | auth | `login`, `logout`, `auth status` | `/auth/*`, `/api/v1/users/me` |
# | admin | `seed-user` | local trusted operator path |
# | workspaces | `ls`, `show`, `use`, `create`, `rename`, `delete` | `/api/v1/workspaces` |
# | workspace | `status`, `skills` | `/api/v1/workspaces/onboarding-status`, workspace skills |
# | workspace env/files | `get`, `set`, `unset`, `ls`, `cat`, `write`, `rm` | `/api/v1/workspaces/{id}/env`, `/files` |
# | projects | `ls`, `create`, `rename`, `delete` | `/api/v1/projects` |
# | profile / appearance | `get`, `set`, `reset` | `/api/v1/personalization`, `/api/v1/appearance` |
# | channels | `list`, `diagnose-telegram`, `link`, `unlink`, `send` | `/api/v1/channels` plus channel routes |
# | mcp | `list`, `show`, `create`, `update`, `delete` | `/api/v1/mcp/servers` |
# | plugins | `scaffold`, `spec`, `validate`, `list`, `enable`, `disable`, `doctor`, `graph`, `reload`, `capabilities`, `slots` | plugin manifests and runtime snapshots |
# | jobs | `list`, `show`, `create`, `delete` | `/api/v1/scheduled-jobs` |
# | models | `ls` | `/api/v1/models` |
# | completions | `autocomplete` | `/api/v1/completions/autocomplete` |
# | conversations | `create`, `send`, `ls`, `show`, `rename`, `delete`, `export` | `/api/v1/conversations`, `/api/v1/chat` |
# | messages | `ls`, `get` by `(conversation_id, index)` | `/api/v1/conversations/{id}/messages` |
# | cost | `summary`, `ledger` | `/api/v1/cost`, `/api/v1/cost/ledger` |
# | audit | `ls`, `show`, `summary` | `/api/v1/audit` |
# | heartbeat | `sync` | `/api/v1/heartbeat/sync` |
# | lcm | `context <conv-id>` | `/api/v1/lcm/conversations/{id}/context` |
# | api | `request`, `openapi`, `ls`, root `METHOD PATH` shorthand | any authenticated backend route |
# | record / replay | `record COMMAND...`, `replay --from FILE` | local fixture capture/replay |
# | fanout / mirror | parallel personas, local-vs-remote SSE diff | local orchestrators |
# | doctor | no verb | local setup + `/api/v1/health` + models |
# </skill-gen>

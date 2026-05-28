---
# pawrrtal-kp50
title: 'feat(api): close gaps surfaced by paw — workspace CRUD, /api/v1 prefix for users, /auth/jwt/logout, event taxonomy'
status: todo
type: feature
priority: high
created_at: 2026-05-27T17:57:23Z
updated_at: 2026-05-27T17:57:23Z
---

Subagents building paw discovered four API gaps:

1. **No POST /api/v1/workspaces.** Today workspaces are seeded as a side-effect of PUT /api/v1/personalization → ensure_default_workspace (backend/app/api/personalization.py:69). paw login has to call PUT /personalization to create one — an undiscoverable side door. Add POST /api/v1/workspaces with WorkspaceCreate {name, path}. Also expose PATCH/DELETE if missing.

2. **/users/me lives at /users/me, not /api/v1/users/me.** FastAPI-Users mounts at prefix='/users' (backend/main.py:198). Inconsistent with the rest of the v1 surface. Re-mount at /api/v1/users and keep /users as a thin compat alias for the frontend.

3. **No /auth/jwt/logout route.** Server cannot revoke the session cookie. Wire fastapi_users.get_auth_router's logout endpoint (or add it manually) so POST /auth/jwt/logout clears the cookie.

4. **Event taxonomy missing 'artifact'.** chat.py:105 and openai_codex/events.py:132 emit type='artifact' events the documented taxonomy doesn't enumerate. Also frontend's CHAT_EVENT_TYPES (frontend/features/chat/hooks/use-chat.ts:33-41) lists 'agent_terminated' but no backend emitter exists — confirm it's dead code, remove if so.

## Todos
- [ ] POST /api/v1/workspaces with WorkspaceCreate schema {name, path}
- [ ] PATCH /api/v1/workspaces/{id} (rename / move) — if not already present
- [ ] DELETE /api/v1/workspaces/{id} — confirm exists
- [ ] Re-mount FastAPI-Users users router at /api/v1/users (canonical) + keep /users alias for frontend compat
- [ ] POST /auth/jwt/logout that clears session_token cookie
- [ ] Document full event taxonomy in chat.py docstring incl 'artifact'
- [ ] Audit 'agent_terminated' — emitter or dead code? Remove or document.
- [ ] Update paw to use new canonical paths
- [ ] Bean closure

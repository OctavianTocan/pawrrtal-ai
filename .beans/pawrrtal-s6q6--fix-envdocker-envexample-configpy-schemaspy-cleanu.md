---
# pawrrtal-s6q6
title: Fix .env.docker, .env.example, config.py, schemas.py cleanup
status: completed
type: bug
priority: high
created_at: 2026-05-09T06:52:23Z
updated_at: 2026-05-09T07:01:08Z
parent: pawrrtal-c6tc
---

Boot/operator-facing config fixes. Todos: backend/.env.docker add WORKSPACE_ENCRYPTION_KEY with generation comment so fresh boots stop crashing; fix mislabeled comment on REGISTRATION_SECRET that currently calls itself the encryption key; backend/.env.example replace Chinese mojibake with English mistakenly assume; decide on registration_secret -- delete the field or add a startup WARNING when set so operators know the gate is gone; backend/app/cli/admin_seed.py:29 remove invite_code=settings.registration_secret since the field no longer exists on UserCreate; backend/app/schemas.py:23 delete the empty UserCreate pass subclass and reference BaseUserCreate directly. Optional: add FERNET_KEY pydantic alias for one release as a deprecation bridge.



## Summary of Changes

- backend/.env.docker: replaced bare REGISTRATION_SECRET= line (with mislabeled comment) with proper WORKSPACE_ENCRYPTION_KEY= line and generation comment.
- backend/.env.example: removed REGISTRATION_SECRET section entirely (including the Chinese mojibake comment).
- backend/app/core/config.py: deleted registration_secret field — no callers left now.
- backend/app/cli/admin_seed.py: removed invite_code=settings.registration_secret kwarg.
- backend/app/users.py: deleted no-op UserManager.create() override and unused fastapi_users.schemas import.
- backend/app/schemas.py: kept UserCreate / UserRead / UserUpdate as documented stubs since fastapi-users requires them as the registration / read / update endpoint schemas. Empty subclass with a docstring is the intended extension point.

Verified: no stragglers in source or tests reference registration_secret/invite_code/REGISTRATION_SECRET. Settings boot smoke-tested. Ruff clean across touched files.

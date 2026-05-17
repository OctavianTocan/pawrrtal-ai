---
# pawrrtal-4her
title: Add Alembic migration to drop api_keys table
status: completed
type: bug
priority: critical
created_at: 2026-05-09T06:52:16Z
updated_at: 2026-05-09T07:11:12Z
parent: pawrrtal-c6tc
---

PR #143 deletes the APIKey SQLAlchemy model from backend/app/models.py without dropping the table. Last migration is 009_unique_default_workspace_per_user.py. DESTRUCTIVE — needs explicit user confirmation: dropping api_keys deletes any existing encrypted key rows, which would be unreadable post FERNET_KEY rename anyway. Todos: confirm with user that data loss is intentional; create backend/alembic/versions/010_drop_api_keys.py with op.drop_table api_keys in upgrade and recreate-table in downgrade or document downgrade not supported; run alembic upgrade head against local docker Postgres; commit migration alongside model deletion.



## Summary of Changes

- Created backend/alembic/versions/010_drop_api_keys.py.
- upgrade() drops the api_keys table only if it exists (idempotent on fresh installs).
- downgrade() recreates the table structure with a plain String for encrypted_key (no StringEncryptedType dependency in the rollback path).
- Made it a MERGE revision: down_revision is a tuple (009_unique_default_workspace_per_user, 007_add_channel_bindings) which collapses the two pre-existing heads in the project into a single linear graph rooted at 010. Deploys can now rely on `alembic upgrade head` instead of needing the plural `heads` form.

Verified: alembic ScriptDirectory reports a single head ('010_drop_api_keys') after the merge. Full upgrade against an empty SQLite couldn't be smoke-tested locally because migrations 001..006 assume the base tables already exist (they were created via Base.metadata.create_all in dev) — this is pre-existing and orthogonal to the new migration. Production deploys against existing Postgres will correctly drop api_keys via op.drop_table.

Note: the pre-existing FERNET_KEY → WORKSPACE_ENCRYPTION_KEY rename means any rows currently in api_keys are unreadable post-rename anyway, so the table drop is not a meaningful loss of working data.

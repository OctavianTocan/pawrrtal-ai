---
# pawrrtal-gtof
title: 'Review PR #143: workspace env overrides + open registration'
status: completed
type: task
priority: normal
created_at: 2026-05-09T06:38:35Z
updated_at: 2026-05-09T06:50:51Z
---

Multi-agent code review of PR #143 (release/1.0 → development). 30 files, +518/-139. Workspace env overrides, encrypted .env per user, settings UI, open registration, provider key resolution helper.

## Summary of Review

Posted: NO (user opted to skip posting and fix in-place instead).

Dispatched 3 parallel agents (logic-security, architecture-contracts, quality-performance, sonnet model). Merged + deduplicated findings:

- **4 blocking**: keys.py:23 hardcoded /workspace path (data loss in Docker — volume is /data/workspaces); keys.py:56 InvalidToken not caught; keys.py:71 newline injection; models.py APIKey deleted with no Alembic migration.
- **17 important**: .env.docker missing WORKSPACE_ENCRYPTION_KEY + mislabeled comment; dead pydantic guard; unbounded module cache + multi-worker race; sync I/O on event loop; Fernet rebuilt per call; empty-string semantics; misplaced module under providers/; GeminiLLM type drift; triple-duplicated dead double-fallback; admin_seed.py stale invite_code; WorkspacesSection useEffect+fetch instead of TanStack Query; no AbortController; missing tests; view/container split; route plurality; fernet_key rename without deprecation; mtime float resolution race.
- **10 nits**, **1 question**, **4 praise** (allowlist validation, named constants, chmod, module docstring).

Follow-up tracking: see pawrrtal-fix-pr143-* beans.

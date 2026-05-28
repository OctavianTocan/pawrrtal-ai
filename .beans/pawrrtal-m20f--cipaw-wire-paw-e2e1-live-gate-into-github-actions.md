---
# pawrrtal-m20f
title: 'ci(paw): wire PAW_E2E=1 live gate into GitHub Actions'
status: in-progress
type: task
priority: normal
created_at: 2026-05-27T20:08:18Z
updated_at: 2026-05-27T23:54:36Z
---

Wire the backend/tests/e2e_paw/ suite (PAW_E2E=1) into the CI workflow. Today these tests are gated and only run locally. Need a job that boots a real backend + Postgres and runs the 2 live tests. Parent epic: pawrrtal-6cnv (paw v1).

## Summary of Changes

Added `.github/workflows/paw-verify.yml` — a self-hosted GitHub Actions job that runs `pytest tests/e2e_paw/` with `PAW_E2E=1`. The suite boots its own uvicorn subprocess against a tmpdir SQLite DB via the existing `live_backend` fixture, so no extra Postgres service container is needed in CI (matches the actual conftest behavior; Postgres parity is tracked as a separate follow-up).

Triggers on PRs + pushes to `development`/`main` that touch `backend/**`, `.claude/skills/paw/**`, `docs/superpowers/plans/*paw*`, or the workflow file itself. Gated to OctavianTocan + same-repo per `.claude/rules/github-actions/octaviantocan-only-and-self-hosted-runner.md`. Runs on `[self-hosted, openclaw-mini, pawrrtal]`.

Env vars / secrets:
- Hardcoded import-time settings (AUTH_SECRET, GOOGLE_API_KEY, WORKSPACE_ENCRYPTION_KEY, CORS_ORIGINS, DATABASE_URL placeholder, ADMIN_EMAIL, ADMIN_PASSWORD, COOKIE_*).
- `OPENAI_API_KEY` from repo secrets (chat-roundtrip test self-skips when absent).
- `~/.codex/auth.json` on the runner gates the codex test (self-skips when absent).

Pipeline uses `set -o pipefail` with `tee` so `pytest`'s exit code propagates through the log capture. Uploads `paw-verify-output.txt` as an artifact (always) and comments on PR on failure with the last 6000 chars of output.

Also removed the now-completed "CI workflow wiring" line from `.claude/skills/paw/SKILL.md`'s open follow-ups.

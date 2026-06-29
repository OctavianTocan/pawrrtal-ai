# Personal Preferences
<!-- customized for Pawrrtal on 2026-06-29 after agentic-stack v0.18.0 install -->
<!-- re-run: agentic-stack <harness> --reconfigure to update onboarding defaults -->

> **This file is yours.** Edit it any time — it's the first thing your AI
> reads at the start of every session.

## Code style
- Language(s): TypeScript (frontend), Python (backend), Effect TS (backend-ts strangler)
- Explanations: concise
- Lint/format: Biome for TS; Ruff for Python; run gates after substantive edits
- Design system: root `DESIGN.md` + `frontend/app/globals.css` tokens — no ad-hoc Tailwind colors

## Workflow
- Test strategy: test-after (ship tests with features when behavior changes)
- Commit style: conventional commits (`feat:`, `fix:`, `refactor:`, `chore:`)
- Task runner: `just` at repo root (`just dev`, `just check`, `just install`)
- End-to-end claims: use `paw verify` / `paw lab`, not ad-hoc `app.*` imports

## Communication
- Review depth: critical issues only
- Tone: direct, skip pleasantries
- Surface tradeoffs: always

## Constraints
- Stack: Next.js 15 + FastAPI + optional Effect TS on `:8001`; monorepo — keep frontend/backend boundaries
- Never force-push `main` or `development`; rebase before push
- Paw skills live in `.agent/skills/` (canonical); `.agents/skills/` and `.claude/skills/` mirror for harness discovery
- User workspaces are seeded from `backend/templates/workspace/` — do not conflate repo dev brain with runtime workspace layout
- Multi-agent safety: no stash/worktree/branch switches unless explicitly requested

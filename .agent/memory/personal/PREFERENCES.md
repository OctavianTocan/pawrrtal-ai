# Personal Preferences
<!-- customized for Pawrrtal on 2026-06-29 after agentic-stack v0.18.0 install -->
<!-- re-run: agentic-stack <harness> --reconfigure to update onboarding defaults -->

> **This file is yours.** Edit it any time — agents read it every session
> after `.agent/AGENTS.md`.

## Code style

- Language(s): TypeScript (frontend), Python (backend), Effect TS (backend-ts strangler)
- Explanations: concise
- Lint/format: Biome for TS; Ruff for Python; run gates after substantive edits
- Design system: root `DESIGN.md` + `frontend/app/globals.css` tokens — no ad-hoc Tailwind colors
- Fix lint warnings and errors in every file you touch — do not label them "pre-existing"
- Docstrings: contract-only, 1–3 lines on exports; fix inaccurate comments when editing

## Workflow

- Test strategy: test-after (ship tests with features when behavior changes)
- Commit style: conventional commits (`feat(scope): …`, `fix(scope): …`); one concern per commit
- Task runner: `just` at repo root (`just dev`, `just check`, `just install`)
- Run toolchain after substantive edits (`just check`, scoped tests you touched)
- End-to-end claims: `paw verify` / `paw lab` — not ad-hoc `app.*` imports
- Read implementations and official docs/skills before inventing APIs
- Load `agents-md` before creating or editing root or nested `AGENTS.md` files
- Keep root `AGENTS.md` a short pointer; put operational depth in `.agent/skills/`, not monolithic briefings
- Update `DESIGN.md` when you change design tokens in code
- Log technical decisions in `frontend/content/docs/handbook/decisions/` (ADR-style) — beans tie-in optional, not required
- Tasks: `beans create` / `beans update` — never hand-edit `.beans/` frontmatter

## Communication

- Review depth: critical issues only
- Tone: direct, skip pleasantries
- Surface tradeoffs: always
- `/caveman` or "caveman mode": follow `.claude/skills/caveman/SKILL.md`

## UI taste

- External UI references: Pawrrtal naming + theme tokens — no third-party palette copy
- Loaders: skeleton until fetch result is known; capture reusable patterns in `DESIGN.md`
- Scrims: background blur + subtle dark tint (~10–15% black), not flat uniform opacity
- `@octavian-tocan/react-overlay`: compose with header/footer surfaces — not body-only titles

## Constraints

- Stack: Next.js 15 + FastAPI + Effect TS on `:8001`; keep frontend/backend boundaries
- Never force-push `main` or `development`; rebase onto `origin/development` before push
- No backwards-compatibility shims — update callers directly
- Do not extend cookie auth in new `003` slices (profiles + Tailscale is the direction)
- Skills canonical in `.agent/skills/`; harness mirrors (`.agents/`, `.claude/`, `.cursor/plugins/pawrrtal/skills/`) symlink there — edit only `.agent/skills/`
- Path-scoped rules canonical in `.agent/rules/`; load `path-rules` before editing
- User workspaces seed from `backend/templates/workspace/` — do not conflate repo dev brain with runtime workspace layout

## Multi-agent

- No `git stash`, worktree create/remove, or branch switch unless explicitly requested
- On "commit": stage only your changes
- On "push": `git pull --rebase` is OK
- Ignore unrelated WIP in the tree; mention only if relevant
- Spike/experimental work: dedicated git worktree; stay on assigned task
- Do not pivot to files the user has open in parallel IDE sessions

## Ask before

- Destructive or wide-scope work (schema drops, mass deletes, production config)
- Bulk PR close/reopen affecting more than 5 PRs
- Force push to any branch
- Modifying `DESIGN.md` for design-system *policy* (implementation consumes the contract)

## Teaching / Effect arcs

- Effect teaching (`lessons/`, `MISSION.md`): user writes code, agent reviews — no ghost-written handlers
- Effect APIs: `backend/vendor/effect-smol`; layout reference: `backend/vendor/effect-api-layout/` (gitignored — read by explicit path)
- Skip frontend/UI strangler work unless asked; focus on `backend-ts` slices when in teaching mode

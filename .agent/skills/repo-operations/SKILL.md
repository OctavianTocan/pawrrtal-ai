---
name: repo-operations
description: "Use for Pawrrtal repo workflow: beans issue tracker, git and PR policy, multi-agent safety, sentrux architecture gates, extension-boundary summaries, commit conventions, and the no-pre-existing-excuse rule. Load before beans tasks, parallel-agent work, structural refactors, or CI workflow authoring."
---

# Repo operations

Day-to-day repository workflow. Hard coding rules: `code-quality`. VPS runners: `runner-ops`. CI YAML: `github-actions`. Entry contract: `.agent/AGENTS.md`. Personal taste: `memory/personal/PREFERENCES.md`. Stable facts: `memory/semantic/DOMAIN_KNOWLEDGE.md`.

## Boundaries (Always / Ask / Never)

**Always**

- Run `recall.py` before deploy, migration, timestamp, debug, refactor
- Read `extension-boundaries` before providers, channels, tools, plugins, turn orchestration
- Read `paw` skill before using or changing the Paw CLI
- Run `just sentrux` when structure changes

**Ask first**

- Destructive or wide-scope work (schema drops, mass deletes, production config)
- `git worktree` create/remove, branch checkout/switch
- Bulk PR close/reopen > 5 PRs
- `git stash` create/apply/drop
- Force push

**Never**

- Commit secrets
- Backwards-compat shims or re-exports for old consumers
- Mix frontend/backend responsibilities

(See also `memory/personal/PREFERENCES.md` for personal Ask-before list.)

## Quick reference

| Topic | Rule |
|-------|------|
| Tasks | `beans create` / `beans update` — never hand-edit `.beans/` frontmatter |
| Commits | Conventional `feat(scope): …`; one concern per commit; story in message body |
| Protected branches | No merge commits on `main`/`development`; rebase onto `origin/development` before push |
| Warnings | Fix every warning in files you touch — never label "pre-existing" |
| Multi-agent | No stash/worktree/branch switch unless asked; commit only your files |
| Architecture | `just sentrux` when structure changes; frontend ⇏ backend imports |
| Integrations | Read `extension-boundaries` before providers/channels/tools/plugins |
| Docs first | Official docs + shipped `SKILL.md` before inventing APIs |

## Beans issue tracker

Tasks live in `.beans/pawrrtal-<id>--<slug>.md`. Handbook: `frontend/content/docs/handbook/agents/issue-tracker.md`.

```bash
beans create "Short task title"
beans update <id> status in-progress
beans update <id> --body-file /tmp/body.md   # bulk body edits
```

**Bean body style** (junior-engineer actionable):

- `## Goal` — one sentence
- `## Files` — exact paths
- Numbered steps, tables for config, fenced blocks for every command/snippet
- Folder trees for new packages
- Epics: `## How it works` + `## Rules` block

ADRs: `frontend/content/docs/handbook/decisions/`. Domain context: `frontend/content/docs/handbook/agents/domain.md`.

## Git and pull requests

- Small, review-friendly PRs; group related changes only
- Bulk close/reopen **> 5 PRs** → ask user with exact count first
- `just commit` / `just push` when using repo automation
- Fix lint warnings on every file the PR touches

See `git-proxy` skill for commit/push safety constraints.

## Multi-agent safety

Other sessions may be editing in parallel.

- **Do not** `git stash` unless explicitly requested
- **Do not** create/remove `git worktree` or switch branches unless asked
- On **commit** → stage only your changes
- On **push** → `git pull --rebase` is OK; never discard others' work
- Unrecognized WIP files → ignore; mention only if relevant
- Formatting-only churn on files you already touched → auto-include in same commit when commit was requested

## No pre-existing excuse

Never describe a failure as "pre-existing" to justify leaving it broken. Lint warnings, type errors, console errors, and flaky tests in files you touch get fixed. If scope explodes, open a sibling PR and reference it.

Rule file: `.claude/rules/general/no-pre-existing-excuse.md`.

## How we work (nine rules)

Full text: `.claude/rules/general/how-we-work-on-pawrrtal.md`. Summary:

1. Read implementation before editing
2. Trace cause before fixing
3. Update `DESIGN.md` when tokens change in code
4. Reuse established patterns — no parallel mechanisms
5. `cursor-pointer` on interactive elements
6. Run toolchain after every file write
7. Ship tests with behavior changes
8. One concern per commit
9. Ask before destructive or scope-bending work

## Architecture boundaries

**Sentrux layers** (`.sentrux/rules.toml`):

| Stack | Layers |
|-------|--------|
| Frontend | `app → features → ai-elements → ui-primitives → lib` |
| Backend | `entry → api → crud → models → core` |
| Cross | `frontend/*` ⇏ `backend/*` |

```bash
just sentrux    # local; CI posts PR comment on failure
```

**Provider-agnostic tools:**

- Tool implementations → `backend/app/tools/`
- Provider adapters → `backend/app/providers/` (never import tools)
- Turn composition → `backend/app/agents/tool_surface.py`
- Enforced by `scripts/check-no-tools-in-providers.py`

**Multi-file features** → package directory with role-named modules (`provider.py`, `Http.ts`, `Repo.ts`); drop redundant prefixes. Template: `backend/app/providers/gemini_cli/`, `frontend/features/<feature>/`.

**Semantic search first** when CodeGraph/Serena/LSP is available; then `rg`. Rule: `.claude/rules/general/prefer-semantic-code-search.md`.

## Check official docs and skills first

Before integrating a library:

- TanStack: `npx @tanstack/intent@latest list` / `load <pkg>#<skill>`
- Other libs: Context7 + DeepWiki MCPs (`.mcp.json`)
- Pawrrtal: `.agent/skills/_index.md`

Rule: `.claude/rules/general/check-official-docs-and-skills-first.md`.

## UI and frontend guardrails (pointers)

| Topic | Where |
|-------|--------|
| Design tokens | `design-md` skill, `DESIGN.md` |
| User-facing copy | `user-facing-text` |
| Modals / overlays | `@octavian-tocan/react-overlay` header/footer surfaces |
| Icons / SVGs | Dedicated files only — never inline in feature components |
| Dropdown rows | Pointer-down commit via `frontend/hooks/use-pointer-down-commit.ts` |
| Dev console | `node scripts/dev-console-smoke.mjs` — no `console.error` on cold boot |

## Stagehand browser automation

MCP servers: `stagehand-docs`, `context7`, `deepwiki` (`.cursor/mcp.json`). Doc index: https://docs.stagehand.dev/llms.txt — fetch before asserting V3 APIs.

Cursor: `.cursor/rules/stagehand-v3-typescript.mdc`. Claude: `.claude/rules/stagehand/`.

## Electron desktop (summary)

Frontend stays Electron-agnostic via `frontend/lib/desktop.ts`. New desktop features touch **three files in lockstep**: `electron/src/preload.ts`, `electron/src/ipc.ts`, `frontend/lib/desktop.ts`. IPC namespace `desktop:*`; renderer sandboxed.

Details: `electron/README.md`, `workspace-context` skill.

## Related skills

| Skill | When |
|-------|------|
| `agents-md` | Editing AGENTS.md |
| `code-quality` | Authoring/reviewing code |
| `github-actions` | Writing workflow YAML |
| `runner-ops` | VPS runner pool ops |
| `extension-boundaries` | Kernel vs integration placement |
| `paw` | End-to-end verification |

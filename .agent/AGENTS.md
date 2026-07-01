# AGENTS.md — Pawrrtal

**Entry contract** for any agent on this repo. Root `AGENTS.md` and `CLAUDE.md` point here.
This folder is the portable [agentic-stack](https://github.com/codejunkie99/agentic-stack) brain.

One-liner: self-hosted AI agent platform — Next.js (`frontend/`), Python FastAPI (`backend/`), Effect TS strangler (`backend-ts/`). Stable facts live in `memory/semantic/DOMAIN_KNOWLEDGE.md`.

## Session bootstrap

Read in this order:

1. This file
2. `memory/personal/PREFERENCES.md` — how the user works
3. `memory/semantic/DOMAIN_KNOWLEDGE.md` — ports, layout, commands, domain terms
4. `memory/semantic/LESSONS.md` — graduated lessons
5. `protocols/permissions.md` — tool safety

Before deploy, migration, debug, or refactor:

```bash
python3 .agent/tools/recall.py "<short description of the task>"
```

Load full skills from `skills/_index.md` only when triggers match.

## Non-negotiables

- Obey `protocols/permissions.md` — blocked means blocked
- Never commit secrets (`.env`, API keys, credentials)
- Never force-push `main` or `development`; no merge commits on those branches
- Never hand-edit `memory/semantic/LESSONS.md` — use `graduate.py` / `reject.py` / `learn.py`
- Never modify `protocols/permissions.md`
- Load `skills/code-quality/SKILL.md` before writing or reviewing code in this project
- `frontend/*` must not import `backend/*` (sentrux enforces this)

Workflow preferences, git policy, beans, code style, and CI rules are **not** here — see memory and skills below.

## Where depth lives

| Need | Read |
|------|------|
| Personal taste, communication, workflow | `memory/personal/PREFERENCES.md` |
| Commands, ports, structure, auth/deploy facts | `memory/semantic/DOMAIN_KNOWLEDGE.md` |
| Lessons from past mistakes | `memory/semantic/LESSONS.md` + `recall.py` |
| Architecture ADRs (brain-level) | `memory/semantic/DECISIONS.md` |
| Git, beans, multi-agent, sentrux, boundaries | `skills/repo-operations/SKILL.md` |
| Naming, docs, verification while coding | `skills/code-quality/SKILL.md` |
| Local dev / auth / deploy quick lookup | `skills/workspace-context/SKILL.md` |
| `.github/workflows` authoring | `skills/github-actions/SKILL.md` |
| Paw CLI, E2E claims | `skills/paw/SKILL.md` |
| Providers, channels, tools, plugins | `skills/extension-boundaries/SKILL.md` |
| Path-scoped file traps | `rules/**` (`.claude/rules` symlink), `.cursor/plugins/pawrrtal/rules/` |
| Curated onboarding rules | `rules/CURATED.md` |
| Handbook, design system | `frontend/content/docs/`, `DESIGN.md` |

Nested package `AGENTS.md` files (e.g. `frontend/lib/react-overlay/`) override this briefing for work inside those trees.

## Key skills

| Skill | When |
|-------|------|
| `repo-operations` | Beans, git/PRs, multi-agent, sentrux, repo workflow |
| `workspace-context` | Ports, auth, deploy routing — after reading DOMAIN_KNOWLEDGE |
| `code-quality` | Writing or reviewing code |
| `path-rules` | Creating or curating `.agent/rules/**` |
| `agents-md` | Editing AGENTS.md files |
| `github-actions` | CI workflow YAML |
| `paw` | CLI verification, lab flows |
| `extension-boundaries` | Kernel vs integration placement |
| `design-md` | `DESIGN.md` or visual tokens |
| `live-ops` / `runner-ops` | Live deploy / VPS runners |

## Memory map

| Layer | Path | Purpose |
|-------|------|---------|
| Personal | `memory/personal/PREFERENCES.md` | User conventions |
| Working | `memory/working/WORKSPACE.md` | Current task (ephemeral) |
| Working | `memory/working/REVIEW_QUEUE.md` | Lesson candidates pending review |
| Semantic | `memory/semantic/DOMAIN_KNOWLEDGE.md` | Stable repo facts |
| Semantic | `memory/semantic/DECISIONS.md` | Major brain/architecture choices |
| Semantic | `memory/semantic/LESSONS.md` | Graduated lessons (rendered) |
| Rules | `rules/**` | Path-scoped traps (`paths:` globs) |
| Episodic | `memory/episodic/AGENT_LEARNINGS.jsonl` | Raw action log |

## Review queue

`memory/auto_dream.py` clusters episodic entries into candidates. **You** review them.

If `REVIEW_QUEUE.md` shows pending > 10 or oldest > 7 days, batch-review before substantive work:

```bash
python3 .agent/tools/list_candidates.py
python3 .agent/tools/graduate.py <id> --rationale "..."
python3 .agent/tools/reject.py <id> --reason "..."
```

## Skills discovery

- `skills/_index.md` — human registry
- `skills/_manifest.jsonl` — machine metadata
- Load `SKILL.md` only when triggers match; invoke self-rewrite hooks after repeated failures

## Protocols

- `protocols/permissions.md` — before any tool call
- `protocols/delegation.md` — sub-agent handoff
- `protocols/tool_schemas/` — external tool interfaces

## Host-agent CLI tools

| Tool | Use |
|------|-----|
| `recall.py "<intent>"` | Surface lessons before risky work |
| `learn.py "<rule>" --rationale "…"` | Teach a lesson in one shot |
| `memory_reflect.py <skill> <action> <outcome>` | Log significant events |
| `show.py` | Brain dashboard |
| `list_candidates.py` / `graduate.py` / `reject.py` / `reopen.py` | Review queue |
| `retract_lesson.py` | Retire a lesson with audit trail |

## Brain rules

1. Check memory before repeating a corrected mistake.
2. Clear review-queue backlog before new substantive work when over threshold.
3. Log significant actions via `memory_reflect.py`.
4. Update `memory/working/WORKSPACE.md` as you work.
5. Reasoning lives in skills + the host agent — the harness stays dumb on purpose.

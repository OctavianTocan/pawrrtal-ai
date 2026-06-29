# Pawrrtal Plugin

The single home for Pawrrtal's project-specific agent skills and architecture
rules. Skills are canonical in `.agent/skills/` (agentic-stack portable brain).
Legacy discovery paths mirror that tree:

- `.agents/skills/` → `.agent/skills/` (Codex)
- `.claude/skills/` → `.agent/skills/` (Claude Code)
- `.cursor/plugins/pawrrtal/skills/` → `.agent/skills/` (Cursor plugin)

## Contents

### Skills (`skills/`)

Symlinks into `.agent/skills/`. Edit generated skills with `bun run skill-gen:generate`
(output target `.agent/skills/`); hand-written skills live there directly.

| Skill | What it covers |
|---|---|
| `paw` | The Paw CLI command tree, verification suites, and lab/dogfood flows. |
| `paw-extend` | Extending the Paw CLI with new commands and flows. |
| `code-quality` | Naming, signatures, docs, files, and verification across Pawrrtal's three stacks. |
| `domain-effect` | Effect TS conventions for `backend-ts`, including API contracts, services, layers, and tests. |
| `extension-boundaries` | Where channels, providers, tools, plugins, subagents, and context providers live. |
| `live-ops` | Live deployment, Cloudflared, Telegram, database, and real integration verification. |
| `pr-scope-audit` | Auditing whether work is really in a PR and separating repo vs VPS operations. |
| `runner-ops` | Self-hosted GitHub Actions runner operations and Octavian-only gating. |
| `skill-gen` | Generating skills from source-embedded `<skill-gen>` fragments. |
| `taste` | Clean, modern UX, CLI output, Telegram rendering, and tool presentation. |
| `returns` | Guardrail against `dry-python/returns` in the Python backend. |
| `user-facing-text` | Conventions for every string a user reads across channels. |
| `workflow-plan` | Planning ambiguous or multi-step work before implementation. |

### Rules (`rules/`)

Pawrrtal-specific architecture rules, moved here from `.claude/rules/` and
converted to Cursor `.mdc` format:

- `rules/clean-code/` — function design, naming, nesting, named constants,
  Python typing/logging, documentation preservation.
- `rules/github-actions/` — Octavian-only + self-hosted runner gating, safe
  `pull_request_target`, action pinning, workflow-race prevention, PR
  descriptions.

> Note: these rules were moved out of `.claude/rules/`, so Claude Code no longer
> auto-applies them from that path. Cursor loads them from this plugin once the
> plugin is installed.

## Installing

This plugin is checked into the repo for version control. To use it in Cursor,
install it from this directory (`.cursor/plugins/pawrrtal`).

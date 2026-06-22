---
name: agents
paths: [".no-match"]
---

# AGENTS.md — claude-rules

Guide for humans and AI agents working on this repository. Covers philosophy, authoring, naming, categorization, and frontmatter conventions.

## Why This Repo Exists

Every rule here was extracted from something that went wrong. A production crash, a CI timeout that burned a morning, a "works on my machine" that didn't work anywhere else. The repo is a living record of hard-won lessons, not a list of best practices copied from documentation.

Claude Code loads rules from `~/.claude/rules/` and applies them to every conversation. A good rule saves you from repeating the same correction. A bad rule adds noise and gets ignored.

## What Makes a Good Rule

**It exists because something broke.** Rules born from theory ("always use const") are weak. Rules born from a 3 AM incident ("Hermes crashes on `.toSorted()` because it targets ES2022") are strong. If you can't point to the specific failure that motivated the rule, it probably belongs in a linter config, not here.

**It names the anti-pattern.** A rule isn't "use X." It's "here's the subtle way Y will bite you, and here's X as the fix." The bad example matters more than the good one. Claude learns from contrast, not from instruction.

**It's narrow and actionable.** "Write good tests" is a poster, not a rule. "Never use `networkidle` in Playwright — it waits for zero network connections which never happens in SPAs with analytics/WebSocket; use `waitForLoadState('domcontentloaded')` instead" is a rule.

**It has a Verify section.** Every rule ends with a self-check prompt. This is the mechanism by which Claude confirms it applied the rule correctly. Without it, rules are suggestions.

**It includes code examples.** Both bad and good. Concrete, copy-pasteable, with comments explaining the failure mode. Prose alone doesn't stick.

## Naming Rules

File names follow one of two patterns:

**Imperative (most common):** `abort-controller-per-request.md`, `validate-response-shape-at-boundary.md`, `never-override-auth-library-internals.md`
Tells Claude exactly what to do. Use this when the rule is a direct instruction.

**Diagnostic (for debugging/troubleshooting):** `binary-search-error-origin.md`, `check-bookkeeping-before-theory.md`, `timeout-masquerades-as-cancelled.md`
Names the concept or the trap. Use this when the rule is about a diagnostic mindset rather than a single action.

**What to avoid:**

- Category labels as names: `type-safety.md`, `state-safety.md`, `bundle-imports.md`. These are folders, not rules.
- Vague abstractions: `best-practices.md`, `error-handling.md`. Tell me _which_ error, handled _how_.
- Project-specific prefixes when the lesson is general: `rn-hermes-no-es2023.md` when `hermes-no-es2023-array.md` works.

The heading (`# Title`) inside the file should be a complete, descriptive sentence. Not an echo of the filename — a real sentence that could stand alone as advice. "Create a New AbortController Per Request" not "Abort Controller Per Request". "Test Auth Flows Under React StrictMode" not "StrictMode Idempotent".

## Where New Rules Go

Rules are organized by the domain they protect, not by the technology they mention. Ask: "If this rule fires, what part of the codebase is at risk?"

- **`api/`** — HTTP clients, fetch wrappers, SSE/WebSocket connections, response handling at the boundary
- **`auth/`** — Authentication flows, token refresh, session management, login strategies
- **`ci/`** — GitHub Actions, CI pipelines, caching, build timeouts, workflow YAML, deployment
- **`debugging/`** — Diagnostic mindsets, investigation strategies, root cause analysis patterns
- **`error-handling/`** — Error types, error boundaries, recovery strategies, error propagation
- **`figma/`** — Design-to-code translation, component specs from Figma
- **`git/`** — Branching strategies, merge conflicts, rebasing, git workflows
- **`monorepo/`** — Workspace management, package boundaries, shared configs in monorepos
- **`playwright/`** — Playwright-specific E2E patterns and traps
- **`react/`** — React patterns, hooks, rendering, component architecture
- **`stagehand/`** — Stagehand V3 patterns and MCP workflow for AI-driven browser automation
- **`state-management/`** — State libraries, stores, derived state, persistence
- **`sweep/`** — Sweep AI code review integration
- **`testing/`** — Test patterns, mocking strategies, test infrastructure (tool-specific rules go in their own folder, e.g. Playwright)
- **`typescript/`** — Type system patterns, inference, narrowing, declarations
- **`clean-code/`** — Function design, naming, named constants, Python logging/exception narrowing (pawrrtal-specific; relocated to `.cursor/plugins/pawrrtal/rules/clean-code/`)
- **`github-actions/`** — Strict context and design patterns for CI/CD workflows (pawrrtal-specific; relocated to `.cursor/plugins/pawrrtal/rules/github-actions/`)
- **`general/`** — Cross-cutting principles that don't belong to one domain. "Diagnose before workaround." "Verify locally before blaming CI." Rules that apply everywhere because they're about how to think, not what to type.
  Example: `prefer-semantic-code-search.md` tells agents to try semantic code lookup before raw text search when CodeGraph, Serena, or an equivalent tool is available.

Removed in 2026-05 audit because the underlying stack isn't in this repo: `brownfield/`, `expo/`, `react-native/`, `rust/`, `twinmind/`. If you ever ship a React Native or Rust target, restore those folders from `OctavianTocan/claude-rules` upstream.

**When in doubt:** If the rule mentions a specific tool, put it in that tool's folder. If it mentions a mindset or a cross-cutting principle, put it in `general/`. If a folder doesn't exist for the domain, create one — don't stuff it in `general/` to avoid making a decision.

**When porting from upstream:** Skip rules whose paths-globs target stacks this repo doesn't ship (e.g. `**/*.{kt,swift,gradle}` rules don't earn their keep without a native target). Better a small set of always-applicable rules than a long list of rules whose globs never fire.

## Frontmatter Format

Every rule file starts with YAML frontmatter:

```yaml
---
name: Create a New AbortController Per Request
paths: ["**/*.{ts,tsx,js,jsx}"]
---
```

**Fields:**

- `name` — Human-readable slug. Matches the filename (kebab-case). Not read by Claude Code, but used by our linter and for human reference.
- `paths` — Glob patterns that activate this rule. This is the official Claude Code field. Rules without `paths` load unconditionally on every session. Rules with `paths` only load when Claude works with matching files.

**Legacy fields to remove if encountered:** `triggers:`, `description:`, `globs:`, `alwaysApply:`. These are not recognized by Claude Code.

## Rule File Structure

```markdown
---
name: Descriptive Title
paths: ["**/*.{relevant,extensions}"]
---

# Descriptive Title

One paragraph explaining the failure mode and the fix. Lead with the trap, follow with the escape.

## Verify
"Self-check question Claude should ask after applying this rule."

## Patterns

Bad — what goes wrong:
​```language
// the code that causes the incident
​```

Good — the fix:
​```language
// the code that prevents it
​```
```

Keep it under 80 lines. If you need more space, the rule is probably two rules.

## Anti-Patterns in Rule Authoring

**Linter configs dressed as rules.** "Prefer const over let" is an ESLint rule, not a Claude Code rule. If a linter can enforce it, don't put it here.

**Scolding.** "Always remember to..." — Claude doesn't need encouragement. State the constraint and the consequence.

**Overlap.** Two rules covering the same trap from slightly different angles. Merge them. One rule with two examples beats two rules that Claude has to reconcile.

**Stale rules.** If the library version that caused the issue is three major versions ago and the footgun no longer exists, delete the rule. Dead rules are noise.

## Contributing

1. Write the rule following the structure above.
2. Pick the right folder. If none fits, create one.
3. Name the file with an imperative or diagnostic pattern (kebab-case).
4. Add frontmatter with `name` and `paths`.
5. Update the README table in the relevant category section.
6. Commit with a message that names the rule: `add: rule-name-descriptor`.

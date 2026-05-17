---
# pawrrtal-dy4x
title: Prune irrelevant rules and skills from .claude and .agents
status: completed
type: task
priority: normal
created_at: 2026-05-14T07:17:08Z
updated_at: 2026-05-14T08:57:14Z
---

Remove rules in .claude/rules/ and skills in .claude/skills + .agents/skills that target stacks Pawrrtal does not use (RN, iOS/Android native, Maestro, Figma, Zustand, Firebase, pnpm, Vercel). Pawrrtal stack: Next.js 16 + React 19 + Bun + Biome + FastAPI + Agno + Electron + self-hosted GH runner + Vitest/Playwright/Stagehand/pytest.

## Summary of Changes

Audited project (Pawrrtal): Next.js 16 + React 19 + TypeScript + Tailwind 4 + Bun + Biome frontend; FastAPI + Python 3.13 + Agno + Claude Agent SDK backend; Electron wrapper; self-hosted GH runner CI; Vitest/Playwright/Stagehand/pytest; @octavian-tocan/react-overlay for modals; FastAPI-Users JWT auth; bun workspaces (not pnpm). No React Native, no iOS/Android native, no Maestro, no Figma workflow, no Zustand, no Vercel, no Firebase auth.

### Rules removed (.claude/rules/, 34 files)

**CI — iOS/Android/RN/pnpm-specific (12):**
- ci/bundle-js-into-aar.md
- ci/put-gradle-api-calls-inside-dependencies-block.md
- ci/gradle-cache-key-cng.md
- ci/pnpm10-lifecycle-scripts.md
- ci/shutdown-ios-simulators-after-tests.md
- ci/code-signing-disabled-in-ci.md
- ci/dynamic-ios-simulator-detection.md
- ci/gradle-embed-needs-build-type-attribute.md
- ci/detect-android-sdk-self-hosted-runners.md
- ci/metro-oom-prevention.md
- ci/brownfield-cli-over-xcodebuild.md
- ci/no-xcodeversion-in-xcodegen-spec.md

**Debugging — iOS/Android/RN (3):**
- debugging/native-mount-issue-not-js-render.md
- debugging/fmt-consteval-error-means-stale-pod-cache.md
- debugging/readelf-abi-before-fixing-linker-errors.md

**Entire categories — no longer applicable:**
- e2e/ (all 3 files: Maestro/Android/RN-only)
- figma/ (all 5 files: project uses DESIGN.md as source, no Figma workflow)

**State management — Zustand/Kotlin-specific (3):**
- state-management/zustand-immutable-updates.md
- state-management/zustand-setter-stable-ref.md
- state-management/singleton-before-db.md

**Testing — RN (1):**
- testing/mock-react-native-in-vitest.md

**Monorepo — RN (1):**
- monorepo/vitest-mock-flow-types.md (paths was .no-match anyway)

**Auth — Firebase/Notion-specific (3):**
- auth/never-override-auth-library-internals.md
- auth/use-factory-functions-for-login-strategies.md
- auth/per-agent-auth-isolation.md

**General — pnpm/agentic-stack-specific (3):**
- general/pnpm-only-package-manager.md
- general/pnpm-store-dir-on-external-drive.md
- general/never-hand-edit-lessons.md

**Cursor-vendored — Vercel/other-project-specific (2):**
- cursor-vendored/no-vercel-bypass-secret.mdc
- cursor-vendored/download-banner-padding.mdc

### Rules kept

All other rules (180 .md + 24 .mdc) — covers TypeScript, React, Next.js, FastAPI/Python, Biome, Bun monorepo, Stagehand/Playwright, Vitest, Electron, error handling, auth patterns generally, CI for GH Actions, sentrux, design system, sweep/PR review.

### Skills removed (1)

- setup-matt-pocock-skills (.agents/skills/ + .claude/skills/ symlink) — one-time scaffolding skill; the per-repo Matt Pocock setup (Agent skills block in CLAUDE.md, frontend/content/docs/handbook/agents/) is already in place. Note: skills-lock.json entry was reverted by an external mechanism after my edit — left as-is per system signal.

## 2026-05-14 follow-up: research on rule loading

Researched how Claude Code loads .claude/rules/ files. Findings:

- Rules with paths: frontmatter inject lazily on Read (per Anthropic issue #23478) — not on Write.
- Rules WITHOUT paths or with paths: ['**/*'] load on every session.
- Cursor-vendored .mdc files cost zero context (loader only handles .md).
- Best-practice articles converge on: CLAUDE.md ≤200 lines for universals only, scope domain rules with paths.

This repo's CLAUDE.md is 456 lines (≈2× recommended ceiling). Largest hidden cost is the always-on CLAUDE.md content, not the rule files themselves.

### Done in follow-up
- Deleted general/how-we-work-on-pawrrtal.md (pure duplicate of how-we-work-on-pawrrtal.md; ~120 lines saved per session).

### Open follow-ups (pending user decision)
- Move 'Agent-Loop Testing Philosophy' section (~80 lines in CLAUDE.md) to .claude/rules/testing/ with paths: ['backend/**/*.py'].
- Move 'Curated Claude rules (Pawrrtal)' citation list (~50 lines) to a docs/ index file.

## 2026-05-14 finalization

Executed remaining follow-ups:

1. Extracted CLAUDE.md 'Agent-Loop Testing Philosophy' section (~95 lines) → .claude/rules/testing/agent-loop-testing-philosophy.md with paths: ['backend/**/*.py', 'backend/tests/**']. Now loads only when editing backend Python.
2. Extracted CLAUDE.md 'Curated Claude rules (Pawrrtal)' citation list (~80 lines, including Monorepo/Biome, Git/PRs, AI review subsections, and Vendored Cursor rules notes) → docs/curated-claude-rules.md.
3. Replaced both sections in CLAUDE.md (via AGENTS.md symlink target) with a single 'Claude rules index' paragraph (1 line of prose + 2 markdown links).
4. Fixed stale citation to deleted how-we-work-on-pawrrtal.md → now points to how-we-work-on-pawrrtal.md.

### Results
- AGENTS.md/CLAUDE.md: 456 → 283 lines (≈38% smaller, still 80 over the 200-line target).
- Net per-session always-on token savings: deleted duplicate (~120 lines) + extracted backend testing philosophy (~95 lines) + extracted citation index (~80 lines) ≈ 295 lines no longer paid on every conversation.
- Backend testing rule now loads lazily only when editing backend/**/*.py.
- Citation index now opt-in (docs/curated-claude-rules.md).

### Still over budget
AGENTS.md is 283 lines — best practices target ≤200. Remaining bloat: 'Learned Workspace Facts' (~25 lines, project memory; could move to docs/), Feb 2026 'Recent Activity' tables under claude-mem-context (~75 lines, auto-injected by claude-mem skill), and 'Collaboration / Safety Notes' (~20 lines). The Feb tables are agent-rewritten so removing them is futile. Worth a follow-up bean only if AGENTS.md keeps growing.

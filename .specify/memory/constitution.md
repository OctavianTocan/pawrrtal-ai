<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles: none
Added sections: none
Expanded policy: Pawrrtal Constraints — added Hatchet (self-hosted, Tailscale-only)
  as the mandated durable automation/workflow orchestration substrate.
Templates requiring updates:
- reviewed (no change needed): .specify/templates/plan-template.md
- reviewed (no change needed): .specify/templates/tasks-template.md
- reviewed (no change needed): .specify/templates/spec-template.md
- reviewed (no change needed): .specify/templates/checklist-template.md
Follow-up TODOs: none
-->

# Pawrrtal Constitution

## Core Principles

### I. Evidence Before Claims

Every spec, plan, and implementation claim MUST be grounded in current repository,
runtime, or documentation evidence. Agents MUST inspect the relevant local code
and project rules before proposing architecture or changing behavior. For live
or user-visible behavior, source inspection alone is not enough when a local or
production probe is practical. Unknowns MUST remain explicit instead of being
filled with guesses.

### II. Preserve Architecture Boundaries

Frontend work MUST stay in `frontend/` and communicate with the backend only via
established API endpoints, authenticated fetch helpers, or TanStack Query flows.
Backend work MUST preserve the FastAPI layer boundaries in `backend/app/`.
Optional integrations MUST stay outside the generic kernel: channels, providers,
tools, plugins, subagents, context providers, and turn orchestration changes must
follow `.agents/skills/extension-boundaries/SKILL.md`.

### III. Design System Consistency

User-facing UI MUST follow the Pawrrtal design system in `DESIGN.md` and the
tokens in `frontend/app/globals.css`. Specs and plans that alter UI behavior,
copy, layout, color, spacing, motion, or reusable loading states MUST identify
the affected design-system rule and update `DESIGN.md` when the rule changes.
Literal one-off color palettes, ad-hoc radius scales, and copied third-party
branding are not acceptable.

### IV. Gates Travel With the Change

Each implementation plan MUST name the smallest meaningful verification gate for
the change. Backend changes normally include focused pytest or type/lint gates;
frontend changes normally include focused Vitest, typecheck, Biome, or browser
smoke gates; architecture changes include sentrux/import-boundary checks when
relevant. New user-facing behavior requires tests or a documented reason why a
different proof is stronger. Warnings discovered in touched surfaces MUST be
fixed or split into a tracked sibling task instead of dismissed.

### V. Reviewable, Incremental Delivery

Specs, plans, tasks, commits, and PRs MUST be small enough to review without
reconstructing the whole codebase. Work should be sliced by independently
testable user story, contract, or subsystem. Cross-cutting rewrites, speculative
abstractions, and duplicated "V2" surfaces require explicit justification in the
plan's complexity section. Existing user work in the git tree MUST be preserved.

## Pawrrtal Constraints

- Primary stack: Next.js App Router, TypeScript, Tailwind CSS v4, React 19,
  FastAPI, SQLAlchemy, Alembic, pytest, Bun, uv, and just.
- Canonical commands come from `justfile`; plans should prefer `just check`,
  `just test`, `just arch`, `bun run design:lint`, and scoped variants already
  documented in `AGENTS.md`.
- CI and workflow plans MUST follow the Octavian-only actor gate and self-hosted
  runner policy documented in `AGENTS.md` and `.cursor/plugins/pawrrtal/rules/github-actions/`.
- Task tracking in `.beans/` MUST be managed through the `beans` CLI only.
- Public or user-facing URLs MUST be verified before sharing.
- Durable automation and workflow orchestration MUST run on the self-hosted
  **Hatchet** instance (private, Tailscale-only — never publicly exposed; see the
  "Hatchet (self-hosted, Tailscale-only)" plan in Agent Plans), not ad-hoc inline
  or cron orchestration. Rationale: Hatchet provides durable, retryable, observable
  workflows, which is materially more robust as Pawrrtal's automations grow.

## SpecKit Workflow

- SpecKit artifacts live under `specs/[###-feature]/`.
- `/speckit-specify` should capture user value and acceptance behavior without
  implementation details.
- `/speckit-plan` should map the accepted spec onto Pawrrtal's real frontend,
  backend, docs, design, and test surfaces.
- `/speckit-tasks` should produce exact file paths, independent story slices,
  and the verification command for each slice.
- Once a SpecKit task set becomes active project work, create or update matching
  beans with the `beans` CLI when persistent tracking is needed.

## Governance

This constitution governs SpecKit-generated specs, plans, tasks, checklists, and
implementation work in Pawrrtal. `AGENTS.md`, `DESIGN.md`, and path-scoped rules
remain authoritative for detailed engineering behavior; this file summarizes the
non-negotiable constraints SpecKit must enforce.

Amendments require updating this file and any affected SpecKit templates in the
same change. Versioning follows semantic versioning: MAJOR for removed or
redefined principles, MINOR for new principles or materially expanded policy,
and PATCH for wording clarifications. Every `/speckit-plan` output MUST include
a Constitution Check before Phase 0 research and re-check after Phase 1 design.

**Version**: 1.1.0 | **Ratified**: 2026-06-15 | **Last Amended**: 2026-06-22

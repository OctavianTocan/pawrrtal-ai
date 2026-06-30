# Implementation Plan: Effect CLI Boundaries

**Branch**: `development` / SpecKit feature `005-effect-cli-boundaries` | **Date**: 2026-06-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-effect-cli-boundaries/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Harden the existing Bun-backed `@pawrrtal/cli` foundation by making every CLI boundary contract explicit and Effect-backed. The feature keeps the current command surface and package layout, but replaces hand-rolled config/output/error boundary handling with schema-backed decode and encode paths, uses Effect `Config`/`ConfigProvider` for environment descriptors, and updates generated CLI guidance so future command groups follow the same pattern.

This is not another CLI redesign and not a feature-command expansion. It is a focused boundary-hardening pass for `packages/paw-cli`.

## Technical Context

**Language/Version**: TypeScript `6.0.3` through Bun workspace scripts. CLI runtime is Bun-first. Effect v4 target is `effect@4.0.0-beta.92`, `@effect/platform-bun@4.0.0-beta.92`, and `@effect/vitest@4.0.0-beta.92`. Npm's default `latest` tag currently points to Effect v3, so v4 beta selection must use the explicit `4.0.0-beta.*` line.

**Primary Dependencies**: `effect` for `Schema`, `Config`, `ConfigProvider`, `Context`, `Effect`, `Layer`, `Cause`; `effect/unstable/cli` for command parsing; `@effect/platform-bun` for Bun services and `BunRuntime`; `@effect/vitest` and Vitest for package tests. `effect/unstable/encoding` is researched but deferred until a command emits streaming records.

**Storage**: No database. Reads and writes only CLI-local TOML config under project-local `paw.toml`, resolved state roots, and profile/user config files. Persisted config remains non-secret only.

**Testing**: Package typecheck and tests through `bun run --filter @pawrrtal/cli check`; focused gate through `just paw-cli-check`; generated-skill drift through `bun run skill-gen:check`; full repo gate through `UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check` when broader confidence is needed. Use `@effect/vitest` for Effect service/schema paths and process integration tests for real Bun CLI behavior.

**Target Platform**: Local and CI command-line use for agents and maintainers. No browser UI, backend API runtime, Python CLI runtime, or Node-specific CLI runtime.

**Project Type**: Tooling/CLI package hardening plus generated skill guidance.

**Performance Goals**: Keep `paw --help`, `paw --version`, `paw context --json`, and `paw doctor --json` effectively instant for local use after dependencies are installed. Schema decode/encode should be bounded to the small first-slice CLI documents and config files.

**Constraints**: Keep Bun-first source execution; do not add `@effect/platform-node` or `node:*` imports to `packages/paw-cli/src`; preserve documented config precedence; keep auth and secret persistence out of scope; do not touch frontend behavior or gates; do not reintroduce old Python CLI compatibility; update generated skill guidance through `packages/ci/skill-gen/`.

**Scale/Scope**: Existing first-slice commands only: `doctor`, `context`/`whoami`, and `completions`. Boundary contracts cover current structured outputs, expected errors, config inputs, package metadata, and command metadata consumed by generated skills. Future feature commands reuse the pattern but are not added here.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Evidence Before Claims**: PASS. Plan evidence comes from `specs/005-effect-cli-boundaries/spec.md`, `.specify/memory/constitution.md`, current `packages/paw-cli` source/tests, `backend-ts/CONVENTIONS.md`, `backend/vendor/effect-smol`, and live npm metadata for the v4 beta line.
- **Preserve Architecture Boundaries**: PASS. Scope is restricted to `packages/paw-cli`, generated `.agent/skills/domain-cli`/`paw` output through skill-gen, `scripts/paw` only if boundary wiring requires it, and local SpecKit artifacts. No frontend, backend API, provider, channel, or old Python CLI work.
- **Design System Consistency**: PASS. No UI, copy surface, design tokens, or `DESIGN.md` changes.
- **Gates Travel With The Change**: PASS. The plan names package-local CLI checks, generated skill drift checks, and full repo verification.
- **Reviewable, Incremental Delivery**: PASS. This is a boundary-hardening pass over an existing package, not a cross-repo rewrite or command expansion.

## Project Structure

### Documentation (this feature)

```text
specs/005-effect-cli-boundaries/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── config-resolution.md
│   ├── structured-output.md
│   └── skill-guidance.md
└── tasks.md
```

### Source Code (repository root)

```text
packages/
└── paw-cli/
    ├── package.json
    ├── src/
    │   ├── Main.ts
    │   ├── Cli.ts
    │   ├── Commands.ts
    │   ├── Helpers/
    │   │   ├── CommandMetadata.ts
    │   │   ├── Config.ts
    │   │   ├── Errors.ts
    │   │   ├── Output.ts
    │   │   ├── Version.ts
    │   │   └── ...
    │   ├── Infrastructure/
    │   │   └── ActiveContext.ts
    │   ├── Modules/
    │   │   ├── Context/
    │   │   ├── Doctor/
    │   │   └── Completions/
    │   └── Skills/
    │       └── Fragments.ts
    └── test/
        ├── unit/
        ├── integration/
        └── fixtures/

packages/
└── ci/
    └── skill-gen/

.agent/
└── skills/
    ├── paw/
    └── domain-cli/
```

**Structure Decision**: Keep schemas next to the owning CLI concept rather than creating a parallel descriptor framework. `Helpers/Config.ts` owns config/input schemas, `Helpers/Errors.ts` owns schema-backed CLI error classes and error JSON shape, `Helpers/Output.ts` owns schema-backed structured rendering, `Helpers/CommandMetadata.ts` owns metadata validation, `Helpers/Version.ts` owns package-manifest validation, and `Modules/<Name>/Domain.ts` owns module result schemas such as doctor health reports.

## Complexity Tracking

No constitution violations require justification. This feature reduces existing boundary complexity by replacing manual parsing and duplicated output/error shapes with shared contracts.

## Post-Design Constitution Check

- **Evidence Before Claims**: PASS. Design artifacts cite local source facts and researched Effect APIs.
- **Preserve Architecture Boundaries**: PASS. Contracts and quickstart remain scoped to the CLI package and generated skills.
- **Design System Consistency**: PASS. No UI scope.
- **Gates Travel With The Change**: PASS. Quickstart includes package, skill-gen, and repo gates.
- **Reviewable, Incremental Delivery**: PASS. Stories can ship independently: schema contracts first, config resolution second, output/error encoding third, skills last.

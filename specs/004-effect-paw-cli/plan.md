# Implementation Plan: Effect Paw CLI

**Branch**: `development` / SpecKit feature `004-effect-paw-cli` | **Date**: 2026-06-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-effect-paw-cli/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Build a new standalone Paw CLI package from scratch at `packages/paw-cli` using Effect v4 CLI primitives, then make `scripts/paw` and `just paw` resolve to that package. The first implementation slice proves the CLI framework, not feature parity: root help/version, global conventions, `doctor`, `context`, `completions`, output/error contracts, generated `paw` and `domain-cli` skills, and removal of the old Python CLI runtime path.

The old Python CLI under `backend/app/cli/paw/` is historical reference only. It must be removed as a supported runtime path rather than bridged, shimmed, or ported command-for-command.

## Technical Context

**Language/Version**: TypeScript 6.x through Bun workspace scripts as the canonical compiler baseline, so the CLI is prepared for TypeScript 7 semantics without depending on an in-progress compiler port. CLI implementation uses Effect v4; planning reference is the pulled `backend/vendor/effect-smol` source at `effect@4.0.0-beta.92`. Existing `backend-ts` remains on its current Effect pin and is not migrated by this feature.

**Primary Dependencies**: `effect/unstable/cli` for typed command trees, arguments, flags, examples, help, aliases, global flags, and shell completions; `@effect/platform-node` for Node platform services and runtime entry wiring; `packages/ci/skill-gen/` for generated skills; Bun workspaces for package scripts. `@typescript/native-preview` / `tsgo` may be added as an optional comparison typecheck after the package exists, but normal TypeScript remains the required gate.

**Storage**: No database. CLI-local state uses filesystem config/cache paths only. `PAW_HOME` wins when set; otherwise the CLI may use XDG config/cache roots when present and home-directory defaults when they are absent. Generated skills are written by `skill-gen` to `.agent/skills/`.

**Testing**: Package-local TypeScript 6 typecheck and Vitest tests for command contracts, output modes, health/context/completions, input-source validation, and no-Python fallback. Repo gates: `bun run skill-gen:check`, package-local `bun run --filter '@pawrrtal/cli' check`, `UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check`. Optional local comparison gate: `bun run --filter '@pawrrtal/cli' typecheck:tsgo` once `@typescript/native-preview` is available. Full frontend/browser gates are not part of the default CLI loop.

**Target Platform**: Local and CI command-line usage for agents and maintainers on the same OS/runtime families already supported by Pawrrtal development. No browser UI and no frontend runtime dependency.

**Project Type**: Tooling/CLI package plus launcher/gate updates.

**Performance Goals**: Root `paw --help` and `paw --version` should finish in under 1 second after dependencies are installed. Package-local checks should avoid backend server startup and frontend build work.

**Constraints**: No old Python CLI shim, no command-for-command porting, no frontend-only hooks in the CLI-only gate, no separate CLI skill generator outside `packages/ci/skill-gen/`, no unsupported `paw-extend` guidance after the one-time Python cleanup, and no required TypeScript-Go gate until its diagnostics match the canonical TypeScript check for this package.

**Scale/Scope**: Initial package includes root conventions and three built-in command surfaces: `doctor`, `context`, and `completions`. Future feature-owned command groups are added only when their feature needs them.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Evidence Before Claims**: PASS. Planning evidence came from `specs/004-effect-paw-cli/spec.md`, `.specify/memory/constitution.md`, current `package.json`, `justfile`, `scripts/paw`, `backend/pyproject.toml`, generated `.agent/skills/*`, `packages/ci/skill-gen/`, live `ntn` help output, and pulled `backend/vendor/effect-smol` CLI docs/source.
- **Preserve Architecture Boundaries**: PASS. New CLI lives in `packages/paw-cli`; old Python CLI removal is limited to `backend/app/cli/paw`, related tests, launcher references, and generated old CLI skills. Frontend stays untouched.
- **Design System Consistency**: PASS. No UI, visual design, tokens, copy surfaces, or `DESIGN.md` changes are planned.
- **Gates Travel With The Change**: PASS. The plan names package-local tests, skill generation drift checks, old CLI removal checks, and repo `just check`.
- **Reviewable, Incremental Delivery**: PASS. The plan starts with the root CLI framework and generated skills before later feature command groups. No feature command parity is included.

## Project Structure

### Documentation (this feature)

```text
specs/004-effect-paw-cli/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-contract.md
│   ├── command-metadata.schema.json
│   └── skill-generation.md
└── tasks.md
```

### Source Code (repository root)

```text
packages/
├── paw-cli/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vitest.config.ts
│   ├── src/
│   │   ├── Main.ts
│   │   ├── Cli.ts
│   │   ├── Commands.ts
│   │   ├── Helpers/
│   │   │   ├── Config.ts
│   │   │   ├── Errors.ts
│   │   │   ├── ExitCode.ts
│   │   │   ├── InputSource.ts
│   │   │   ├── Options.ts
│   │   │   └── Output.ts
│   │   ├── Infrastructure/
│   │   │   └── BackendClient.ts
│   │   ├── Skills/
│   │   │   └── Fragments.ts
│   │   └── Modules/
│   │       ├── Context/
│   │       │   ├── Command.ts
│   │       │   └── Domain.ts
│   │       ├── Completions/
│   │       │   └── Command.ts
│   │       └── Doctor/
│   │           ├── Checks.ts
│   │           ├── Command.ts
│   │           └── Domain.ts
│   └── test/
│       ├── integration/
│       │   ├── bin.test.ts
│       │   ├── completions.test.ts
│       │   ├── context.test.ts
│       │   ├── doctor.test.ts
│       │   ├── help.test.ts
│       │   └── harness.ts
│       └── unit/
│           ├── config.test.ts
│           ├── input-source.test.ts
│           ├── output.test.ts
│           └── skill-fragments.test.ts
├── ci/
│   └── skill-gen/
│       └── src/
│           ├── index.ts
│           ├── scan.ts
│           ├── output.ts
│           └── dynamic-fragments.ts    # one-time generic extension, if needed

scripts/
└── paw

backend/
├── pyproject.toml
├── app/
│   └── cli/
│       ├── admin_seed.py
│       ├── commit.py
│       ├── migrate_workspace_env.py
│       └── paw/                 # removed by this feature
└── tests/
    ├── paw/                     # removed or replaced by packages/paw-cli/test
    └── e2e_paw/                 # removed unless a later feature reintroduces live CLI E2E

.agent/
└── skills/
    ├── paw/
    │   └── SKILL.md
    └── domain-cli/
        └── SKILL.md
```

**Structure Decision**: Use `packages/paw-cli` with package name `@pawrrtal/cli`. Follow the comcom `tcc` package convention: `Main.ts` is the executable bin entrypoint, `Cli.ts` wires the root command and runtime layers, `Commands.ts` is the only top-level command registry, shared behavior lives in `Helpers/` and `Infrastructure/`, and each top-level command group owns a `src/Modules/<Name>/Command.ts` plus local domain/support files. Keep it outside `backend-ts/` so the CLI package can be installed, tested, and evolved without inheriting backend API server migration concerns. Keep it outside `backend/` because the Python CLI is being retired rather than ported.

## Complexity Tracking

No constitution violations require justification. The new package is not speculative expansion; it is the core scope requested by the feature and replaces an existing Python CLI runtime path.

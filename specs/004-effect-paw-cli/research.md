# Phase 0 Research: Effect Paw CLI

## Decision: Build the new CLI as `packages/paw-cli` / `@pawrrtal/cli`

**Rationale**: The spec requires the CLI to be fully abstracted away and not governed by the old Python command tree. A root `packages/` workspace package matches the current repo shape (`packages/ci/skill-gen`) and keeps CLI work independent from `backend-ts` server migration concerns and `frontend/` checks.

**Alternatives considered**:

- `backend/app/cli/paw`: rejected because it preserves the old Python CLI ownership model.
- `backend-ts/packages/cli`: rejected because it couples the CLI package to the API strangler workspace even though the CLI must be a general project operator surface.
- `scripts/paw` as the implementation: rejected because shell scripts should be launchers only, not the typed command framework.

## Decision: Follow the comcom `tcc` module layout for the CLI package

**Rationale**: The closest proven Effect CLI shape is the comcom `tcc` package: executable `Main.ts`, root/runtime wiring in `Cli.ts`, one top-level command registry in `Commands.ts`, shared helpers under `Helpers/`, runtime adapters under `Infrastructure/`, and top-level command groups under `src/Modules/<Name>/Command.ts` with local support files. Pawrrtal should copy that package shape rather than using a flat `src/*.ts` plus `commands/` folder.

**Alternatives considered**:

- Flat `src/commands/*.ts`: rejected because it does not match the established module layout the user wants agents to recognize.
- One folder per command under package root: rejected because it spreads implementation details outside the package's source boundary.
- Backend-style route folders: rejected because this package is a CLI package, not an HTTP API service.

## Decision: Use Effect v4 `effect/unstable/cli` as the command framework

**Rationale**: The pulled `backend/vendor/effect-smol` tree is at `effect@4.0.0-beta.92`, and its CLI docs show the intended model: `Command.make`, typed `Argument` and `Flag`, shared parent flags through `Command.withSharedFlags`, examples via `Command.withExamples`, aliases via `Command.withAlias`, command composition through `Command.withSubcommands`, and runtime execution through `Command.run` with platform services. This directly matches the spec's need for Effect command modules as the runtime source of truth, with lightweight module-owned metadata for help consistency, generated skills, and completions.

**Alternatives considered**:

- Typer/Python: rejected because the old Python CLI is removed by this feature.
- A custom parser: rejected because Effect v4 already provides typed flags, args, nested commands, help, aliases, and completions.
- Reusing backend HTTP route contracts as the CLI contract: rejected because the first CLI slice is an operator surface, not a backend route parity project.

## Decision: Use TypeScript 6.x as canonical and TypeScript-Go as optional

**Rationale**: The CLI should be ready for TypeScript 7 without depending on the in-progress native compiler port. TypeScript 6.x is the required package typecheck baseline. TypeScript-Go / `@typescript/native-preview` is viable as an optional package-local comparison gate because it targets TypeScript 7-era compiler behavior and can catch compatibility issues early, but it is not the required gate until it can be installed reliably and its diagnostics match `tsc` for `packages/paw-cli`.

**Planned shape**: package scripts include canonical `typecheck` using TypeScript 6.x. Add `typecheck:tsgo` only as an optional comparison script after the package exists and dependency installation is confirmed. CI and implementation tasks should not depend on `tsgo` until the comparison has matched on this package for multiple iterations.

**Alternatives considered**:

- Stay on TypeScript 5.9: rejected because the user asked to use TypeScript 6.0 or newer to prepare for v7.
- Make TypeScript-Go the only compiler gate: rejected because it is still in progress and its npm package availability could not be verified in this environment.
- Skip TypeScript-Go entirely: rejected because it is useful early signal for eventual TypeScript 7 adoption.

## Decision: Add a small dynamic-fragment path to `packages/ci/skill-gen/`

**Rationale**: The spec requires generated `paw` and `domain-cli` skills to stay aligned with the real CLI surface and to use the same `packages/ci/skill-gen/` package as the rest of Pawrrtal. Static `//<skill-gen>` fragments are useful for code-changing guidance, but operational usage must be generated from module-owned command metadata and skill fragments exported beside the Effect command modules to avoid drift. Extending `skill-gen` inside the existing package preserves one generator and one drift check.

**Planned shape**: keep existing marker scanning, then merge in dynamic fragments exported by `packages/paw-cli/src/Skills/Fragments.ts`. The dynamic fragments are derived from the package's module metadata and use the same parsed fragment shape and output rules as scanned fragments, so `bun run skill-gen:generate` and `bun run skill-gen:check` remain the only public commands.

**Alternatives considered**:

- Hand-written `paw` and `domain-cli` skills: rejected because the skills would drift.
- A separate `paw skill-gen` command: rejected because the user explicitly asked to use the existing `skill-gen` package.
- Scraping rendered `--help` output only: rejected because help text alone does not capture package layout, ownership rules, tests, or extension workflow guidance needed for `domain-cli`.

## Decision: Make `.agent/skills/` the generated skill output for this plan

**Rationale**: Current `package.json` routes `skill-gen:generate` and `skill-gen:check` to `.agent/skills`, and `.agent/skills/skill-gen/SKILL.md` names `.agent/skills/` as the canonical generated output. The new `paw` and `domain-cli` skills should follow the current repo-local convention.

**Alternatives considered**:

- `.cursor/plugins/pawrrtal/skills`: rejected for this feature because it is no longer the current root script target.
- `.agents/skills`: rejected as a direct target because current scripts and user-invoked skills use `.agent/skills`.

## Decision: Remove the old Python CLI as part of the feature

**Rationale**: The spec now requires full removal rather than parallel support. The removal surface is `backend/app/cli/paw/`, `backend/tests/paw/`, `backend/tests/e2e_paw/`, the `paw` console script in `backend/pyproject.toml`, `scripts/paw` Python execution, `just paw` assumptions, and generated Python CLI skill fragments. Unrelated Python utility CLIs such as `commit.py`, `admin_seed.py`, and `migrate_workspace_env.py` are not part of this feature.

**Alternatives considered**:

- Keep a compatibility shim for unsupported commands: rejected because it lets the old CLI keep defining the roadmap.
- Port all existing commands first: rejected because the feature explicitly starts fresh and lets future features add command groups when needed.
- Leave old tests skipped: rejected because skipped old CLI tests would make removal ambiguous and noisy.

## Decision: Borrow `ntn` conventions as CLI principles, not commands

**Rationale**: Live `ntn 0.16.0` inspection showed durable conventions worth adopting: noun command groups with verb subcommands, root `doctor`, identity/context checks, shell completions, rich help with scope/examples/notes/environment variables, `--verbose` for source-chain diagnostics, `--json` and `--plain` output modes, and clear input-source rules for `--content`, stdin, and editor fallback. Pawrrtal should reuse those principles without copying Notion-specific names or API behavior.

**Alternatives considered**:

- Copy `ntn` command names broadly: rejected because Pawrrtal's domain is different.
- Ignore `ntn` and rely only on the old Paw CLI: rejected because the user asked for `ntn` inspiration and the old CLI is being removed.

## Decision: Standardize output, errors, and config before feature commands

**Rationale**: Future command groups need a stable base. The first package slice will implement shared output helpers, structured errors, active context resolution, config precedence, health check state, and input-source validation before any product feature commands are introduced.

**Output contract**:

- Data goes to stdout.
- Progress, warnings, prompts, and errors go to stderr.
- Human output is default.
- `--json` and `--plain` are mutually exclusive where both exist.

**Exit code contract**:

- `0`: success, including health commands with warnings when the command itself completed.
- `1`: internal, local, or config error.
- `2`: usage, validation, or ambiguous input source.
- `4`: auth, permission, or active-context denial.
- `5`: backend, network, external process, or dependency failure.
- `6`: future assertion or verification failure.

**Alternatives considered**:

- Preserve old Python CLI exit codes exactly: rejected because this is a redesign.
- Let each command choose output and exit semantics: rejected because agents need a predictable automation surface.

## Decision: Keep the default verification loop CLI/backend-only

**Rationale**: The user wants the frontend preserved but out of the way while backend/base work proceeds. The CLI package gate should be package-local plus `skill-gen` drift checking and repo structural checks. Frontend checks remain in full-repo gates when frontend files are touched.

**Alternatives considered**:

- Always run full frontend checks from the CLI package gate: rejected because it violates the spec's "frontend should not annoy backend/base work" direction.
- Remove frontend files or scripts: rejected because the user explicitly does not want the frontend removed.

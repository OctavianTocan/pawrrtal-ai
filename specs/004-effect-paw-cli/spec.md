# Feature Specification: Effect Paw CLI

**Feature Branch**: `004-effect-paw-cli`

**Created**: 2026-06-29

**Status**: Draft

**Input**: User description: "Redesign the Paw CLI from scratch as its own abstract package. Do not port existing commands just because they exist. Let future features add CLI behavior when they need it. Fully remove the old Python CLI. Generate and check the operational CLI usage skill plus a domain CLI coding skill through the same `packages/ci/skill-gen/` package used by the rest of Pawrrtal. Ground planning in the current effect-smol Effect v4 CLI approach. Keep frontend work out of the backend/base workflow for now. Inspect the local `ntn` CLI and borrow durable principles from it: resource command groups, health and identity commands, explicit output modes, rich help, completions, visible config/env overrides, and clear input-source behavior."

## Clarifications

### Session 2026-06-29

- Q: What runtime/distribution shape should the first CLI slice use? → A: Bun-first source CLI.
- Q: What should be the canonical source of command behavior? → A: Effect command modules.
- Q: Should `paw doctor` perform live backend probes by default? → A: Local-only by default.
- Q: Should the first slice persist auth material or secrets? → A: No secret/auth persistence.
- Q: What config file format should the first slice use? → A: TOML config files.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start With A Clean CLI Package (Priority: P1)

As a Pawrrtal maintainer, I want the new CLI to begin as its own small package with a stable root command and extension points, so the CLI becomes a reusable project surface instead of a migration list for old commands.

**Why this priority**: The CLI package is the foundation for every later command. If it starts as a parity port, it will accidentally decide future product shape before the backend/base architecture is ready.

**Independent Test**: Can be fully tested by installing or running only the new CLI package and confirming that the root command, help, version, and empty command inventory work without requiring the frontend or the old Python CLI.

**Acceptance Scenarios**:

1. **Given** a clean checkout with the new CLI package installed, **When** a maintainer runs the root command help, **Then** the CLI describes its current command surface without listing legacy commands that have not been intentionally reintroduced.
2. **Given** the old Python Paw CLI has been removed, **When** a maintainer invokes the supported `paw` entrypoint, **Then** it resolves to the new CLI package without falling back to the deleted implementation.
3. **Given** a developer is working only on the CLI package, **When** they run the package's local verification gate, **Then** the gate does not require frontend build, lint, or browser checks.

---

### User Story 2 - Generate Agent Skills From The Real CLI (Priority: P1)

As a coding agent, I want generated skills for using and changing the CLI that match the actual command tree, package layout, extension rules, flags, arguments, output modes, examples, and exit behavior, so I can operate and modify the CLI correctly without guessing or reading unrelated source.

**Why this priority**: The CLI is meant to make Pawrrtal easier for agents to modify. Stale usage or coding instructions would make the CLI actively harmful.

**Independent Test**: Can be fully tested by changing a command description or package extension rule, running the drift check, confirming it fails, regenerating the skills through `packages/ci/skill-gen/`, and confirming the check passes with the updated skill text.

**Acceptance Scenarios**:

1. **Given** the CLI command surface changes, **When** the skill-gen check runs before regeneration, **Then** it reports the generated operational CLI skill as stale.
2. **Given** the generated operational skill is refreshed, **When** an agent reads the `paw` skill, **Then** the skill contains the current command names, flags, arguments, examples, output modes, config needs, and verification guidance.
3. **Given** the CLI package extension rules or layout change, **When** the skill-gen check runs before regeneration, **Then** it reports the generated `domain-cli` skill as stale.
4. **Given** a command or extension rule is removed from the real CLI package, **When** generated skills are checked, **Then** removed behavior is not allowed to remain documented as available.

---

### User Story 3 - Let Features Own Their CLI Additions (Priority: P1)

As a feature author, I want to add a CLI command group only when my feature needs one, so the CLI stays open to future capabilities without defining the product roadmap up front.

**Why this priority**: The CLI should be an enabling surface, not a central place that predicts every future feature.

**Independent Test**: Can be fully tested by adding one intentionally tiny command group through the documented extension path and confirming the root command, help output, generated usage skill, and local gate include it without editing unrelated command groups.

**Acceptance Scenarios**:

1. **Given** a new backend/base feature needs a command, **When** its command group is added through the CLI extension path, **Then** the root CLI exposes that command group without requiring a rewrite of existing command groups.
2. **Given** a feature has no command-line workflow yet, **When** the CLI package is released, **Then** that feature is not forced to invent placeholder commands.
3. **Given** two features add independent command groups, **When** either command group changes, **Then** the other command group's behavior and generated usage text remain unchanged.

---

### User Story 4 - Keep Backend/Base Work Quiet From Frontend Gates (Priority: P2)

As a backend/base maintainer, I want the CLI and backend/base verification loop to avoid frontend hooks and scripts unless frontend files are intentionally in scope, so I can make architectural progress without being interrupted by unrelated UI checks.

**Why this priority**: The frontend should stay in the repo because parts of it are valuable, but it should not dominate the early backend/base and CLI redesign loop.

**Independent Test**: Can be fully tested by running the backend/base CLI gate after a CLI-only change and confirming it completes without invoking frontend-only checks while the full-repo gate remains available separately.

**Acceptance Scenarios**:

1. **Given** a change touches only the CLI package, **When** the developer runs the CLI/backend-base gate, **Then** the gate skips frontend-specific checks.
2. **Given** a change intentionally touches frontend files, **When** the developer chooses the full gate, **Then** frontend checks still run.
3. **Given** the frontend remains in the repository, **When** CLI package work happens, **Then** no frontend files need to be deleted or visually redesigned as part of this feature.

---

### User Story 5 - Provide Stable Operator Contracts (Priority: P2)

As a human or automated operator, I want predictable CLI output, error, exit-code, and config behavior, so scripts and agents can rely on the CLI as later command groups appear.

**Why this priority**: A small CLI with stable conventions is more useful than a large command tree with ambiguous results.

**Independent Test**: Can be fully tested by running representative success, validation-error, runtime-error, and machine-readable-output cases and confirming they follow the documented contract.

**Acceptance Scenarios**:

1. **Given** a command succeeds, **When** it exits, **Then** the exit code and output format match the documented success contract.
2. **Given** a command receives invalid input, **When** it exits, **Then** the user sees a concise actionable error and the process returns a non-zero validation exit.
3. **Given** a command supports machine-readable output, **When** the machine-readable mode is requested, **Then** the output can be parsed without human-only decoration.

---

### User Story 6 - Follow Proven Agent CLI Conventions (Priority: P2)

As an agent or human operator, I want the new CLI to follow predictable conventions already proven by local agent-facing tools, so every command feels discoverable, scriptable, and safe without needing hidden repo knowledge.

**Why this priority**: The CLI is supposed to become a stable operator surface for future Pawrrtal features. Borrowing proven conventions prevents each command group from inventing its own grammar, help shape, and automation behavior.

**Independent Test**: Can be fully tested by inspecting root help, one command-group help page, one command help page, the health command, the identity/context command, completions, and machine-readable output for consistent conventions.

**Acceptance Scenarios**:

1. **Given** a maintainer opens root or command help, **When** they read it, **Then** command groups are organized as nouns with verb subcommands and include scope, examples, notes, and relevant environment variables where applicable.
2. **Given** an agent needs automation output, **When** it runs a supported command with machine-readable output, **Then** structured output is printed without scraping human prose.
3. **Given** setup or dependency state is degraded, **When** the health command runs, **Then** it reports pass, warning, and failure states explicitly instead of collapsing every non-perfect state into a generic failure.
4. **Given** a command accepts body or document input, **When** multiple input sources are supplied, **Then** the CLI rejects the ambiguous request and explains the accepted input-source choices.

### Edge Cases

- A generated usage skill exists but the source command group that produced it has been removed.
- A generated domain skill exists but the package extension rule or source layout it describes has changed.
- A command changes aliases, defaults, or examples without updating generated usage output.
- A feature wants to add a command that conflicts with an existing command group name or alias.
- The frontend dependency tree is broken while a CLI-only or backend/base-only gate runs.
- A script, doc, hook, launcher, or skill still points at the removed Python CLI after the new package becomes the supported `paw` entrypoint.
- The retired `paw-extend` skill remains generated from old Python CLI fragments after the one-time Python CLI cleanup is complete.
- A command supports multiple input sources and the caller supplies more than one source in a single invocation.
- A cached or discovered capability source is stale or unavailable; the CLI must say whether it used cached knowledge, live knowledge, or no knowledge.
- A non-interactive environment reaches a command path that would otherwise open an editor.
- A machine-readable command fails halfway through and must return parseable error information or clearly produce no machine-readable payload.
- A command requires local config, but no config file or profile exists yet.
- A command is deprecated or replaced by a feature-owned successor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The new Paw CLI MUST be specified and built as a fresh CLI package, not as a direct port of the existing Python CLI command tree.
- **FR-002**: The CLI package MUST provide a root command with help, version, and command discovery behavior before feature-specific commands are added.
- **FR-003**: The old Python Paw CLI MUST be fully removed as part of this feature, including unsupported entrypoints, command modules, Python-only CLI tests, launcher references, and generated skill fragments that only describe the old implementation.
- **FR-004**: The CLI package MUST NOT include a compatibility shim or fallback path that delegates unsupported commands to the old Python CLI.
- **FR-005**: The CLI package MUST NOT expose legacy commands solely for parity; each command group must be justified by a current feature workflow or operator need.
- **FR-006**: The CLI package MUST define a stable command ownership model where future features can add command groups without editing unrelated command groups.
- **FR-007**: The CLI package MUST define consistent output modes for human-readable and machine-readable use.
- **FR-008**: The CLI package MUST define consistent exit-code categories for success, validation failure, expected runtime failure, and unexpected failure.
- **FR-009**: The CLI package MUST define a consistent config/profile contract that can support later feature-owned settings without centralizing all future configuration decisions.
- **FR-010**: The CLI package MUST generate the operational `paw` agent usage skill from the actual CLI command surface rather than from hand-written duplicated usage text.
- **FR-011**: The CLI package MUST generate a `domain-cli` agent skill that teaches agents how to change, extend, test, and review the new CLI package.
- **FR-012**: Both generated CLI skills MUST be produced by the existing `packages/ci/skill-gen/` package and written to the same generated skill output used by Pawrrtal's other repo-local skills.
- **FR-013**: Module-owned command metadata, help text, or source-adjacent skill fragments MUST feed `packages/ci/skill-gen/`; this feature MUST NOT introduce a separate one-off skill generator for the CLI.
- **FR-014**: The generated operational `paw` skill MUST include command groups, command descriptions, arguments, flags, aliases, examples, output modes, exit behavior, config needs, and verification commands.
- **FR-015**: The generated `domain-cli` skill MUST include package layout, command ownership rules, extension workflow, testing expectations, output/error conventions, and skill-generation hygiene.
- **FR-016**: The repository MUST provide a check that fails when either generated CLI skill is stale, missing, or still documents removed command behavior.
- **FR-017**: The generated skills MUST remain safe for agents to follow from a clean checkout, including setup prerequisites and the smallest reliable verification gate.
- **FR-018**: CLI package verification MUST have a backend/base path that does not run frontend-specific hooks or scripts for CLI-only changes.
- **FR-019**: A full-repository verification path MUST remain available for changes that intentionally touch frontend behavior or release-wide gates.
- **FR-020**: The spec and follow-up plan MUST treat the existing Python Paw CLI as historical reference material only, not as a compatibility target or runtime dependency.
- **FR-021**: The follow-up plan MUST use the current pulled effect-smol Effect v4 CLI documentation and examples as the implementation reference for typed command composition, shared flags, nested command groups, examples, help output, and platform runtime wiring.
- **FR-022**: Command help text, generated operational skill text, generated domain skill text, and any user-facing command names MUST use the same wording for the same concept.
- **FR-023**: The first implementation slice MUST prove that adding or changing one small command updates help, generated skills, and the drift check together.
- **FR-024**: Resource-oriented commands MUST use noun command groups with verb subcommands; short aliases such as `ls` or `rm` are allowed only when they are common, documented, and do not replace the canonical verb.
- **FR-025**: Root help, command-group help, and command help MUST expose scope, examples, notes, and relevant environment variables when those details affect successful use.
- **FR-026**: The CLI MUST provide a global verbose mode that expands diagnostics and source chains while keeping default errors concise and actionable.
- **FR-027**: The CLI MUST provide a health command that reports passed checks, warnings, and failures separately, including degraded-but-usable states.
- **FR-028**: The CLI MUST provide an identity or active-context command so agents can confirm which profile, workspace, session, or backend target they are about to operate against; `paw whoami` MUST be available as an alias for the same active-context meaning.
- **FR-029**: The CLI MUST provide shell completion generation for at least `zsh` and `bash`.
- **FR-030**: Commands that accept document, body, or bulk input MUST define mutually exclusive input sources such as explicit flag value, file or stdin, and interactive editor fallback.
- **FR-031**: Interactive editor fallback MUST only happen in an interactive terminal; non-interactive callers must receive a clear validation error and an explicit non-interactive alternative.
- **FR-032**: Commands that support automation MUST keep human output, structured output, and tabular plain output distinct, with progress, warnings, and errors separated from parseable data.
- **FR-033**: Config and environment overrides MUST be visible from command help, and each documented environment variable must map to a real command behavior or config setting.
- **FR-034**: If a command uses cached discovery, generated indexes, or live capability metadata, it MUST say when the data is stale, unavailable, or loaded from cache.
- **FR-035**: The CLI package MUST use TypeScript 6.x or newer as its canonical TypeScript baseline and MAY include TypeScript-Go as an optional comparison gate only after the normal TypeScript gate remains canonical.
- **FR-036**: The first CLI slice MUST use a Bun-first source entrypoint, with the package `bin` resolving to the TypeScript source entrypoint and no compiled `dist/` or dual Node runtime required for MVP.
- **FR-037**: Effect command modules MUST be the canonical source of command behavior. Each command group owns its Effect command in `src/Modules/<Name>/Command.ts` and may export lightweight metadata or skill fragments from that module area, but this feature MUST NOT introduce a separate descriptor-first framework that generates the command tree.
- **FR-038**: `paw doctor` MUST be local-only by default in the first slice. It validates CLI/package/config/cache/profile/generated-skill state and backend target resolution, but it MUST NOT require or perform backend network reachability checks unless a later explicit opt-in or feature-owned command adds that behavior.
- **FR-039**: The first CLI slice MUST NOT persist auth material, tokens, cookies, API keys, or other secrets. Profile and config files may store only non-secret context such as profile name, backend target, labels, and local defaults; `paw context` reports auth state as `not_applicable` or `unknown` until a later feature specifies authentication.
- **FR-040**: The first CLI slice MUST use TOML for project-local and user/profile config files. The project-local file is `paw.toml`; user/profile config files live under the resolved CLI state root and use TOML.

### Key Entities

- **CLI Package**: The standalone package that owns the root Paw command, common conventions, command composition, and package-local verification.
- **Command Group**: A feature-owned set of related commands exposed through the root CLI.
- **Command Metadata**: Lightweight descriptive data exported from command modules for generated skills, tests, and drift checks. Runtime command behavior is owned by the Effect command module, not by a separate descriptor registry.
- **skill-gen Package**: The existing `packages/ci/skill-gen/` generator that scans source-adjacent fragments, merges skills by name, writes generated `SKILL.md` files, and checks for missing, changed, or stale generated skills.
- **Operational CLI Skill**: The generated `paw` skill that teaches agents how to use the supported CLI as an operator.
- **Domain CLI Skill**: The generated `domain-cli` skill that teaches agents how to change, extend, test, and review the CLI package.
- **Skill Drift Check**: The verification step that compares generated usage skills against the current command surface and fails on stale output.
- **Backend/Base Gate**: The focused verification path for CLI and backend/base work that deliberately avoids frontend-only checks.
- **Full-Repo Gate**: The broader verification path that includes frontend checks when the touched change requires them.
- **Retired Python CLI**: The old Python Paw CLI implementation and generated maintenance skill sources, which may be studied during planning but must not remain as the supported runtime path.
- **CLI Convention Contract**: The shared grammar and help/output/error expectations that every command group follows.
- **Health Check**: A named diagnostic check with pass, warning, or failure state and a clear next step.
- **Active Context**: The current profile, workspace, session, backend target, or other operator context that affects command behavior.
- **Input Source**: One accepted source for command body content, such as an explicit flag value, stdin, file path, or interactive editor.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can run root help and version for the new CLI package from a clean checkout in under 30 seconds after dependencies are installed.
- **SC-002**: 100% of command groups exposed by the new CLI package appear in the generated `paw` skill with examples and verification guidance.
- **SC-003**: An intentional one-line command help or extension-rule change causes the skill-gen drift check to fail before regeneration and pass after regeneration.
- **SC-004**: A CLI-only change can complete its focused backend/base verification path without invoking frontend-specific build, lint, browser, or design-system checks.
- **SC-005**: Adding a tiny new command group requires changes only in the new command group, its package registration point, generated skill output, and tests.
- **SC-006**: The generated `paw` skill contains zero commands that are not exposed by the real CLI command surface.
- **SC-007**: The generated `domain-cli` skill contains the current package layout, extension workflow, and verification gate for changing the CLI.
- **SC-008**: The supported `paw` entrypoint has zero runtime dependency on the old Python CLI after this feature lands.
- **SC-009**: At least one success case, one validation-error case, one expected runtime-error case, and one machine-readable-output case are covered by the first CLI package test slice.
- **SC-010**: Root help, one command-group help page, and one command help page each include examples plus any relevant environment variables.
- **SC-011**: The first health command reports at least one pass state and can represent a warning state without hiding it as success, without requiring a running backend.
- **SC-012**: The first active-context command can be run in human, structured, and plain output modes when context exists.
- **SC-013**: Shell completion generation succeeds for at least two supported shells.
- **SC-014**: A body-input command rejects ambiguous multiple input sources and documents the accepted alternatives.
- **SC-015**: The supported package entrypoint runs from the Bun-backed TypeScript source entrypoint without requiring a compiled distribution directory.
- **SC-016**: Inspecting the first-slice config/profile files reveals no persisted tokens, cookies, API keys, or secret values.
- **SC-017**: A maintainer can define non-secret defaults in `paw.toml` and the CLI resolves them according to the documented config precedence.

## Assumptions

- The new CLI feature receives its own SpecKit feature because it is a focused package redesign, while `003-pawrrtal-overhaul` remains the broader application overhaul spec.
- The package will use Pawrrtal's current project-standard Effect v4 CLI approach during planning and implementation; the user explicitly requested effect-smol research for this.
- The old Python Paw CLI is removed in this feature rather than kept as a fallback, bridge, or parallel supported command surface.
- The existing `packages/ci/skill-gen/` package is the canonical generator for CLI skills, matching the rest of Pawrrtal's generated skill workflow.
- The operational skill keeps the established `paw` skill name, while the code-changing skill uses the repo's `domain-*` convention as `domain-cli`.
- The old Python-generated `paw-extend` guidance is retired as a one-time cleanup step; `domain-cli` teaches the new CLI package after that cleanup, not the old Python removal.
- The local `ntn` CLI version inspected for convention inspiration was `0.16.0`; Pawrrtal should borrow durable command principles, not Notion-specific command names.
- Frontend code stays in the repository and can be worked on later, but this feature's default loop avoids frontend-only gates unless frontend files are intentionally touched.
- The first CLI implementation is optimized for repository-local use by agents and maintainers; external Node/npm distribution can be specified later if it becomes a real product need.
- The first `doctor` command proves local CLI readiness only; live backend health checks can be specified later as an explicit opt-in or as part of the feature that needs them.
- Authentication and credential storage are intentionally deferred until a feature-owned command needs backend-authenticated behavior.
- Config files use TOML because they are expected to be edited by humans and agents.

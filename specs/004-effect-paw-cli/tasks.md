# Tasks: Effect Paw CLI

**Input**: Design documents from `specs/004-effect-paw-cli/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Include tests for new CLI behavior because the spec requires proof for root behavior, output contracts, generated skills, local-only doctor, no-secret config, and old Python CLI removal.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently after the foundational phase.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the isolated CLI workspace and align design artifacts with the post-clarify decisions.

- [ ] T001 Update clarify-derived design drift in `specs/004-effect-paw-cli/plan.md`, `specs/004-effect-paw-cli/research.md`, `specs/004-effect-paw-cli/data-model.md`, `specs/004-effect-paw-cli/contracts/cli-contract.md`, `specs/004-effect-paw-cli/contracts/skill-generation.md`, and `specs/004-effect-paw-cli/quickstart.md`
- [ ] T002 Add `packages/paw-cli` to the root Bun workspace list in `package.json`
- [ ] T003 Create Bun-first CLI package manifest with TypeScript 6.x, Effect v4, Vitest, and `bin.paw` pointing to `src/Main.ts` in `packages/paw-cli/package.json`
- [ ] T004 [P] Create TypeScript configuration for the CLI package in `packages/paw-cli/tsconfig.json`
- [ ] T005 [P] Create Vitest configuration for the CLI package in `packages/paw-cli/vitest.config.ts`
- [ ] T006 [P] Create the comcom-style CLI source folders under `packages/paw-cli/src/Helpers/`, `packages/paw-cli/src/Infrastructure/`, `packages/paw-cli/src/Modules/Context/`, `packages/paw-cli/src/Modules/Completions/`, `packages/paw-cli/src/Modules/Doctor/`, and `packages/paw-cli/src/Skills/`
- [ ] T007 [P] Create CLI unit and integration test folders under `packages/paw-cli/test/unit/`, `packages/paw-cli/test/integration/`, and `packages/paw-cli/test/fixtures/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared command runtime, test harness, and package contracts required by every user story.

**Critical**: No user story work should begin until this phase is complete.

- [ ] T008 Implement the Bun-first executable entrypoint and Effect runtime wiring in `packages/paw-cli/src/Main.ts`
- [ ] T009 Implement the root `paw` Effect command factory, shared global flags, version wiring, and injectable command list in `packages/paw-cli/src/Cli.ts`
- [ ] T010 Implement the single top-level command registry in `packages/paw-cli/src/Commands.ts`
- [ ] T011 Implement shared exit code constants in `packages/paw-cli/src/Helpers/ExitCode.ts`
- [ ] T012 Implement shared output-mode types and stdout/stderr helpers in `packages/paw-cli/src/Helpers/Output.ts`
- [ ] T013 Implement shared CLI error types and error-to-exit-code mapping in `packages/paw-cli/src/Helpers/Errors.ts`
- [ ] T014 Implement shared option helpers for `--json`, `--plain`, `--verbose`, `--profile`, and `--backend-url` in `packages/paw-cli/src/Helpers/Options.ts`
- [ ] T015 Implement an integration test harness for running the CLI in-process and capturing stdout, stderr, and exit codes in `packages/paw-cli/test/integration/harness.ts`
- [ ] T016 [P] Add unit tests for output mode exclusivity and stream separation in `packages/paw-cli/test/unit/output.test.ts`
- [ ] T017 [P] Add unit tests for error category to exit-code mapping in `packages/paw-cli/test/unit/errors.test.ts`
- [ ] T018 Add the package-level `check`, `typecheck`, `test`, `start`, and optional `typecheck:tsgo` scripts in `packages/paw-cli/package.json`

**Checkpoint**: Foundation ready. The package can run an empty root command through the test harness.

---

## Phase 3: User Story 1 - Start With A Clean CLI Package (Priority: P1) MVP

**Goal**: The new standalone CLI package exposes root help/version and becomes the supported `paw` entrypoint without falling back to Python.

**Independent Test**: From a clean checkout after dependencies are installed, run `bun run --filter '@pawrrtal/cli' start -- --help`, `bun run --filter '@pawrrtal/cli' start -- --version`, and `just paw --help`; none should require frontend startup or the old Python CLI.

### Tests for User Story 1

- [ ] T019 [P] [US1] Add root help and version integration tests in `packages/paw-cli/test/integration/help.test.ts`
- [ ] T020 [P] [US1] Add Bun source `bin` launcher integration tests in `packages/paw-cli/test/integration/bin.test.ts`
- [ ] T021 [P] [US1] Add old Python fallback regression tests in `packages/paw-cli/test/integration/no-python-fallback.test.ts`

### Implementation for User Story 1

- [ ] T022 [US1] Implement root help/version behavior with no legacy command listing in `packages/paw-cli/src/Cli.ts`
- [ ] T023 [US1] Update `scripts/paw` to execute the Bun-backed `@pawrrtal/cli` entrypoint instead of `uv run paw`
- [ ] T024 [US1] Update `justfile` `paw` and `install-paw` behavior to resolve the new launcher in `scripts/paw`
- [ ] T025 [US1] Remove the Python `paw = "app.cli.paw.main:app"` console script from `backend/pyproject.toml`
- [ ] T026 [US1] Remove the old Python CLI runtime package at `backend/app/cli/paw/`
- [ ] T027 [US1] Remove old Python Paw CLI unit tests at `backend/tests/paw/`
- [ ] T028 [US1] Remove old live Python Paw CLI E2E tests at `backend/tests/e2e_paw/`
- [ ] T029 [US1] Add a removal verification script or package test that rejects `app.cli.paw`, `uv run paw`, `backend/app/cli/paw`, and `backend/tests/paw` references in `packages/paw-cli/test/integration/no-python-fallback.test.ts`
- [ ] T030 [US1] Run the US1 verification commands from `specs/004-effect-paw-cli/quickstart.md`

**Checkpoint**: User Story 1 works independently and the supported `paw` entrypoint no longer depends on the old Python CLI.

---

## Phase 4: User Story 2 - Generate Agent Skills From The Real CLI (Priority: P1)

**Goal**: Generated `paw` and `domain-cli` skills stay aligned with the real Effect command modules and package extension rules.

**Independent Test**: Change a command module description or domain guidance, run `bun run skill-gen:check`, observe a drift failure, run `bun run skill-gen:generate`, then confirm `bun run skill-gen:check` passes and generated skills mention the current command surface only.

### Tests for User Story 2

- [ ] T031 [P] [US2] Add tests for CLI module-owned skill fragments in `packages/paw-cli/test/unit/skill-fragments.test.ts`
- [ ] T032 [P] [US2] Add dynamic fragment import tests for skill-gen in `packages/ci/skill-gen/test/dynamic-fragments.test.ts`
- [ ] T033 [P] [US2] Add generated skill drift integration tests in `packages/paw-cli/test/integration/skill-gen.test.ts`

### Implementation for User Story 2

- [ ] T034 [US2] Define module-owned command metadata and skill-fragment helpers in `packages/paw-cli/src/Skills/Fragments.ts`
- [ ] T035 [US2] Add generated `paw` and `domain-cli` skill fragments near the root command in `packages/paw-cli/src/Cli.ts`
- [ ] T036 [US2] Add generated `paw` and `domain-cli` skill fragments for `context`, `doctor`, and `completions` in `packages/paw-cli/src/Modules/Context/Command.ts`, `packages/paw-cli/src/Modules/Doctor/Command.ts`, and `packages/paw-cli/src/Modules/Completions/Command.ts`
- [ ] T037 [US2] Implement generic dynamic fragment loading in `packages/ci/skill-gen/src/dynamic-fragments.ts`
- [ ] T038 [US2] Wire dynamic fragments into the skill-gen pipeline in `packages/ci/skill-gen/src/index.ts`
- [ ] T039 [US2] Update `packages/ci/skill-gen/SPEC.md` to document dynamic fragments from module-owned CLI metadata
- [ ] T040 [US2] Generate the operational CLI skill at `.agent/skills/paw/SKILL.md`
- [ ] T041 [US2] Generate the CLI coding-domain skill at `.agent/skills/domain-cli/SKILL.md`
- [ ] T042 [US2] Remove or retire stale generated `paw-extend` guidance from `.agent/skills/paw-extend/SKILL.md` when it only describes old Python CLI maintenance
- [ ] T043 [US2] Run `bun run skill-gen:generate`, `bun run skill-gen:check`, and `bun run skill-gen:e2e-test`

**Checkpoint**: User Story 2 works independently; generated skills are current and old Python CLI guidance is gone.

---

## Phase 5: User Story 3 - Let Features Own Their CLI Additions (Priority: P1)

**Goal**: Future features can add command groups through one module-owned path without editing unrelated command groups or creating placeholder commands.

**Independent Test**: Add a test-only fixture command group, register it through the same module registry path, and confirm help output, generated metadata, and tests include it without changing existing command groups.

### Tests for User Story 3

- [ ] T044 [P] [US3] Add registry extension tests with a fixture command in `packages/paw-cli/test/unit/command-registry.test.ts`
- [ ] T045 [P] [US3] Add command conflict and alias conflict tests in `packages/paw-cli/test/unit/command-conflicts.test.ts`
- [ ] T046 [P] [US3] Add a test-only fixture command module in `packages/paw-cli/test/fixtures/FixtureCommand.ts`

### Implementation for User Story 3

- [ ] T047 [US3] Implement command registration helpers and conflict validation in `packages/paw-cli/src/Commands.ts`
- [ ] T048 [US3] Update `packages/paw-cli/src/Skills/Fragments.ts` so feature-owned modules can contribute `domain-cli` extension guidance without duplicating runtime behavior
- [ ] T049 [US3] Add `domain-cli` generated guidance for adding a new module under `packages/paw-cli/src/Modules/<Name>/Command.ts` in `packages/paw-cli/src/Skills/Fragments.ts`
- [ ] T050 [US3] Ensure no placeholder or legacy parity command groups are registered in `packages/paw-cli/src/Commands.ts`
- [ ] T051 [US3] Run `bun run --filter '@pawrrtal/cli' test -- command-registry command-conflicts`

**Checkpoint**: User Story 3 works independently; the extension path is proven without adding fake product commands.

---

## Phase 6: User Story 4 - Keep Backend/Base Work Quiet From Frontend Gates (Priority: P2)

**Goal**: CLI-only and backend/base work can run a focused gate that avoids frontend build, browser, and design-system checks.

**Independent Test**: Make a CLI-only change and run the focused gate; it should typecheck and test the CLI, check generated skills, and avoid frontend-only commands.

### Tests for User Story 4

- [ ] T052 [P] [US4] Add package script coverage for `check` behavior in `packages/paw-cli/test/integration/check-script.test.ts`
- [ ] T053 [P] [US4] Add launcher gate regression checks in `packages/paw-cli/test/integration/no-frontend-gate.test.ts`

### Implementation for User Story 4

- [ ] T054 [US4] Add a focused `paw-cli-check` recipe to `justfile`
- [ ] T055 [US4] Add root package scripts for focused CLI checks in `package.json`
- [ ] T056 [US4] Ensure `packages/paw-cli/package.json` `check` runs only CLI package typecheck and tests
- [ ] T057 [US4] Update `specs/004-effect-paw-cli/quickstart.md` with the focused CLI gate command and expected no-frontend behavior
- [ ] T058 [US4] Run `bun run --filter '@pawrrtal/cli' check`, `bun run skill-gen:check`, and `just paw-cli-check`

**Checkpoint**: User Story 4 works independently; frontend checks remain available but are not part of the CLI-only loop.

---

## Phase 7: User Story 5 - Provide Stable Operator Contracts (Priority: P2)

**Goal**: Output, error, exit-code, config/profile, no-secret, and input-source behavior are predictable for humans, agents, and scripts.

**Independent Test**: Run success, validation-error, runtime-error, context output, TOML config precedence, no-secret inspection, and input-source ambiguity tests and confirm they match `contracts/cli-contract.md`.

### Tests for User Story 5

- [ ] T059 [P] [US5] Add TOML config precedence and empty-string tests in `packages/paw-cli/test/unit/config.test.ts`
- [ ] T060 [P] [US5] Add no-secret profile persistence tests in `packages/paw-cli/test/unit/no-secrets.test.ts`
- [ ] T061 [P] [US5] Add input-source ambiguity tests in `packages/paw-cli/test/unit/input-source.test.ts`
- [ ] T062 [P] [US5] Add context output mode tests in `packages/paw-cli/test/integration/context.test.ts`

### Implementation for User Story 5

- [ ] T063 [US5] Implement TOML config resolution for `PAW_HOME`, `PAW_PROFILE`, `PAW_BACKEND_URL`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, project `paw.toml`, and user/profile TOML files in `packages/paw-cli/src/Helpers/Config.ts`
- [ ] T064 [US5] Implement no-secret profile write/read helpers in `packages/paw-cli/src/Helpers/Config.ts`
- [ ] T065 [US5] Implement active-context domain types in `packages/paw-cli/src/Modules/Context/Domain.ts`
- [ ] T066 [US5] Implement `paw context` and `paw whoami` human, JSON, and plain output in `packages/paw-cli/src/Modules/Context/Command.ts`
- [ ] T067 [US5] Implement input-source policy helpers in `packages/paw-cli/src/Helpers/InputSource.ts`
- [ ] T068 [US5] Implement parseable error output behavior for JSON-capable commands in `packages/paw-cli/src/Helpers/Errors.ts` and `packages/paw-cli/src/Helpers/Output.ts`
- [ ] T069 [US5] Update the CLI contract with TOML and no-secret behavior in `specs/004-effect-paw-cli/contracts/cli-contract.md`
- [ ] T070 [US5] Run `bun run --filter '@pawrrtal/cli' test -- config no-secrets input-source context`

**Checkpoint**: User Story 5 works independently; scripts can rely on config, output, and error behavior.

---

## Phase 8: User Story 6 - Follow Proven Agent CLI Conventions (Priority: P2)

**Goal**: The first CLI slice follows the agreed local CLI conventions: noun groups, rich help, local-only doctor, context alias, completions, output modes, and explicit environment variables.

**Independent Test**: Inspect root help, one command help page, `paw doctor --json`, `paw context --json`, `paw whoami --json`, `paw completions bash`, and `paw completions zsh`.

### Tests for User Story 6

- [ ] T071 [P] [US6] Add local-only doctor tests in `packages/paw-cli/test/integration/doctor.test.ts`
- [ ] T072 [P] [US6] Add shell completion tests in `packages/paw-cli/test/integration/completions.test.ts`
- [ ] T073 [P] [US6] Add rich help convention tests in `packages/paw-cli/test/integration/help.test.ts`

### Implementation for User Story 6

- [ ] T074 [US6] Implement health check domain types in `packages/paw-cli/src/Modules/Doctor/Domain.ts`
- [ ] T075 [US6] Implement local-only doctor checks for CLI version, config root, cache root, active profile, backend target resolution, and generated skills in `packages/paw-cli/src/Modules/Doctor/Checks.ts`
- [ ] T076 [US6] Implement `paw doctor` human, JSON, and plain output in `packages/paw-cli/src/Modules/Doctor/Command.ts`
- [ ] T077 [US6] Implement bash and zsh completion generation in `packages/paw-cli/src/Modules/Completions/Command.ts`
- [ ] T078 [US6] Add examples, notes, and environment variable descriptions to root, context, doctor, and completions help in `packages/paw-cli/src/Cli.ts`, `packages/paw-cli/src/Modules/Context/Command.ts`, `packages/paw-cli/src/Modules/Doctor/Command.ts`, and `packages/paw-cli/src/Modules/Completions/Command.ts`
- [ ] T079 [US6] Run the root help, command help, `doctor --json`, `context --json`, `whoami --json`, `completions bash`, and `completions zsh` commands from `specs/004-effect-paw-cli/quickstart.md`

**Checkpoint**: User Story 6 works independently; the first CLI slice feels consistent and discoverable.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Validate the full slice, remove stale references, and keep the review surface tight.

- [ ] T080 [P] Update `specs/004-effect-paw-cli/quickstart.md` with final command names, scripts, and expected output snippets after implementation
- [ ] T081 [P] Update `specs/004-effect-paw-cli/contracts/skill-generation.md` if the implemented dynamic fragment shape differs from the planned shape
- [ ] T082 [P] Verify generated skills do not cite `backend/app/cli/paw/`, `backend/tests/paw/`, `backend/tests/e2e_paw/`, or `paw-extend` in `.agent/skills/paw/SKILL.md` and `.agent/skills/domain-cli/SKILL.md`
- [ ] T083 [P] Verify `package.json`, `justfile`, `scripts/paw`, `backend/pyproject.toml`, and `.agent/skills/` contain no supported runtime reference to the removed Python Paw CLI
- [ ] T084 Run `bun run --filter '@pawrrtal/cli' typecheck`, `bun run --filter '@pawrrtal/cli' test`, `bun run --filter '@pawrrtal/cli' check`, `bun run skill-gen:check`, and `UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check`
- [ ] T085 Run optional `bun run --filter '@pawrrtal/cli' typecheck:tsgo` only after `@typescript/native-preview` is installable and compare diagnostics against canonical TypeScript output
- [ ] T086 Document any deferred external Node/npm distribution work in `specs/004-effect-paw-cli/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **US1 (Phase 3)**: Depends on Foundational; MVP path.
- **US2 (Phase 4)**: Depends on Foundational and is most useful after US1 root commands exist.
- **US3 (Phase 5)**: Depends on Foundational and benefits from US2 skill metadata helpers.
- **US4 (Phase 6)**: Depends on US1 package scripts and launcher.
- **US5 (Phase 7)**: Depends on Foundational; can run after US1 root command exists.
- **US6 (Phase 8)**: Depends on US5 helpers for output/config/context and US1 root command.
- **Polish**: Depends on all selected user stories.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational. No dependency on other stories.
- **User Story 2 (P1)**: Starts after Foundational; root command metadata from US1 makes validation meaningful.
- **User Story 3 (P1)**: Starts after Foundational; use US2 metadata helpers if already available.
- **User Story 4 (P2)**: Starts after US1 because it packages the focused gate.
- **User Story 5 (P2)**: Starts after Foundational; can be developed alongside US1 once root command injection exists.
- **User Story 6 (P2)**: Starts after US5 because `doctor`, `context`, and completions depend on shared output/config behavior.

### Within Each User Story

- Tests first; ensure the targeted test fails before implementation.
- Implement helpers before command modules.
- Implement command modules before launcher or generated-skill validation.
- Run the story checkpoint before moving to the next dependent phase.

---

## Parallel Opportunities

- Setup tasks T004, T005, T006, and T007 can run in parallel after T003.
- Foundational tests T016 and T017 can run in parallel after helpers are stubbed.
- US1 tests T019, T020, and T021 can run in parallel.
- US2 tests T031, T032, and T033 can run in parallel.
- US3 tests T044, T045, and T046 can run in parallel.
- US5 tests T059, T060, T061, and T062 can run in parallel.
- US6 tests T071, T072, and T073 can run in parallel.
- Polish reference checks T080, T081, T082, and T083 can run in parallel.

## Parallel Example: User Story 2

```bash
# Generate tests for the skill generation story in parallel:
Task: "T031 Add tests for CLI module-owned skill fragments in packages/paw-cli/test/unit/skill-fragments.test.ts"
Task: "T032 Add dynamic fragment import tests for skill-gen in packages/ci/skill-gen/test/dynamic-fragments.test.ts"
Task: "T033 Add generated skill drift integration tests in packages/paw-cli/test/integration/skill-gen.test.ts"
```

## Parallel Example: User Story 5

```bash
# Generate independent contract tests in parallel:
Task: "T059 Add TOML config precedence and empty-string tests in packages/paw-cli/test/unit/config.test.ts"
Task: "T060 Add no-secret profile persistence tests in packages/paw-cli/test/unit/no-secrets.test.ts"
Task: "T061 Add input-source ambiguity tests in packages/paw-cli/test/unit/input-source.test.ts"
Task: "T062 Add context output mode tests in packages/paw-cli/test/integration/context.test.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. Stop and validate root help/version plus launcher behavior.
5. Confirm the old Python CLI runtime path is no longer supported.

### Incremental Delivery

1. Add US1 to establish the clean CLI package and launcher.
2. Add US2 so generated skills teach the real CLI surface.
3. Add US3 so future feature-owned command groups have a proven extension path.
4. Add US4 to lock the focused backend/base gate.
5. Add US5 and US6 to finish operator contracts and conventions.

### Parallel Team Strategy

1. One person owns Phase 1 and Phase 2.
2. After Foundational, one person can implement US1 while another starts US5 helper tests.
3. After US1, US2 and US4 can proceed in parallel.
4. After US2, US3 can proceed without touching US2 files except generated skill output.

---

## Notes

- `[P]` tasks touch different files and have no dependency on incomplete tasks in the same phase.
- `[US#]` labels map to user stories in `specs/004-effect-paw-cli/spec.md`.
- Use Bun-first source execution for this feature; do not introduce a compiled `dist/` or dual Node runtime in the first slice.
- Effect command modules are canonical; do not build a descriptor-first command framework.
- `paw doctor` is local-only by default; live backend probes are out of scope for this slice.
- No auth material, cookies, tokens, API keys, or secrets may be persisted by this feature.
- Use TOML for project-local and user/profile config.
- Use the `beans` CLI later if these SpecKit tasks become persistent tracked work.

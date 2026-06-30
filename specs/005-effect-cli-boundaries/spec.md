# Feature Specification: Effect CLI Boundaries

**Feature Branch**: `005-effect-cli-boundaries`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "Figure out how to properly use Effect Schema, Config, and the other useful Effect v4 packages for the Paw CLI. Check `backend/vendor/effect-smol` thoroughly, stop relying on hand-rolled parsing and stringification where Effect gives us better tools, and make a SpecKit specification for this new CLI work after the current CLI foundation is committed and pushed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trust CLI Boundary Data (Priority: P1)

As a Pawrrtal maintainer, I want the CLI to validate and encode every external data boundary through declared contracts, so invalid config, package metadata, command output, and error payloads cannot silently drift from what agents and scripts expect.

**Why this priority**: The CLI is becoming an agent-facing operator surface. If its JSON, config, and error shapes are hand-assembled in several places, future commands will repeat the same drift and safety problems.

**Independent Test**: Can be tested by feeding invalid config and command-output fixtures to the CLI boundary checks and confirming each failure is reported as a typed, actionable CLI error rather than an unchecked runtime failure or silently accepted partial value.

**Acceptance Scenarios**:

1. **Given** a user config file contains an unsupported value shape, **When** the CLI reads it, **Then** the CLI rejects it with a clear config error that names the failing source.
2. **Given** a command supports structured output, **When** an agent requests structured output, **Then** the returned document matches the command's declared public shape.
3. **Given** a command fails with an expected validation or config problem, **When** structured error output is requested or diagnostics are rendered, **Then** the error category, message, hint, and verbose details follow the same declared error shape.

---

### User Story 2 - Resolve Configuration Safely (Priority: P1)

As an agent or human operator, I want active profile, state-root, environment, and file-backed config resolution to be predictable and visibly sourced, so I can know exactly which context the CLI is using before it changes anything.

**Why this priority**: The CLI will eventually run backend/base operations. Ambiguous profile or backend-target resolution can lead agents to operate against the wrong local context.

**Independent Test**: Can be tested by setting flags, environment variables, project config, profile config, and user config in different combinations and confirming the active-context command reports the documented winner and source.

**Acceptance Scenarios**:

1. **Given** the same setting is present in multiple supported sources, **When** the CLI resolves active context, **Then** the highest-precedence source wins and the result reports that source.
2. **Given** an environment variable is empty or whitespace-only, **When** config is resolved, **Then** it is treated as unset.
3. **Given** a config file cannot be parsed or decoded, **When** the CLI starts a command that needs context, **Then** the command exits with a config failure instead of continuing with a guessed value.

---

### User Story 3 - Add Commands Without Recreating Boundary Rules (Priority: P2)

As a future feature author, I want new command groups to reuse the same config, output, input, and error boundary contracts, so each feature can focus on its workflow instead of inventing one-off parsing and rendering conventions.

**Why this priority**: The first CLI slice intentionally stayed small. The next commands need a durable way to grow without repeating manual boundary code.

**Independent Test**: Can be tested by adding a tiny command group with one structured output and one expected failure, then confirming it uses the shared boundary rules and appears correctly in generated CLI guidance.

**Acceptance Scenarios**:

1. **Given** a new command group returns structured data, **When** its test fixture changes the output shape without updating the declared contract, **Then** verification fails.
2. **Given** a new command group reads environment-backed settings, **When** tests supply a temporary config provider, **Then** the command resolves settings without mutating the real process environment.
3. **Given** a new command group documents output and error behavior, **When** generated skills are checked, **Then** the guidance matches the declared command contracts.

---

### User Story 4 - Teach Agents The Correct Effect Pattern (Priority: P2)

As a coding agent, I want the generated `domain-cli` skill to explain the schema/config-first CLI pattern, so future changes follow the real Effect v4 approach instead of copying earlier hand-rolled code.

**Why this priority**: Pawrrtal depends on generated skills for agent continuity. If the skill teaches the old pattern, the codebase will drift back immediately.

**Independent Test**: Can be tested by changing the boundary guidance or a command contract and confirming the skill generation check detects stale guidance.

**Acceptance Scenarios**:

1. **Given** the CLI boundary pattern changes, **When** generated skills are checked before regeneration, **Then** the drift check fails.
2. **Given** an agent reads `domain-cli`, **When** it needs to add a command, **Then** it is instructed to define the command's external data contract before adding ad hoc parsing or rendering code.
3. **Given** the CLI uses a Bun-backed runtime, **When** an agent reads the generated guidance, **Then** it does not recommend a Node-specific runtime path for the Paw CLI.

### Edge Cases

- A TOML config file parses successfully but contains values with the wrong type.
- A command returns a value that cannot be encoded into its documented structured output.
- A package manifest is missing or has a non-string version value.
- A structured error omits a required public field or includes verbose details when verbose diagnostics were not requested.
- Multiple config sources define the same value and one of the higher-precedence sources is empty.
- A future command tries to parse environment variables directly instead of using the shared config boundary.
- A generated skill still teaches the manual parsing or direct stringification pattern after the CLI boundary contract changes.
- A useful Effect package exists in the local vendor source but is unrelated to CLI boundary work and should not be added to this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CLI MUST declare public data contracts for active context, config source summaries, health reports, structured command output, and structured expected errors.
- **FR-002**: The CLI MUST validate unknown config-file, environment-derived, package-metadata, and command-output data against the relevant declared contract before the data is trusted or printed as structured output.
- **FR-003**: The CLI MUST encode structured command output through the declared public contract before writing structured output to stdout.
- **FR-004**: The CLI MUST encode structured expected error output through the declared public contract before writing structured error output to stderr.
- **FR-005**: The CLI MUST preserve the existing documented config precedence order: explicit flags, environment variables, project-local config, profile config, user config, and built-in defaults.
- **FR-006**: Empty or whitespace-only config values MUST be treated as unset across all supported config sources.
- **FR-007**: The CLI MUST report which source supplied each resolved active-context value without exposing secret material.
- **FR-008**: The CLI MUST continue rejecting secret-like persisted config keys and MUST keep auth or credential persistence out of this feature.
- **FR-009**: The CLI MUST provide a deterministic test path for environment-backed settings that does not rely on mutating the real process environment.
- **FR-010**: The CLI MUST distinguish source-read failures, schema/contract validation failures, usage failures, expected runtime failures, and unexpected defects in its public error categories.
- **FR-011**: Future command groups MUST be able to reuse the shared boundary contracts for structured output, structured errors, config resolution, and input-source validation.
- **FR-012**: Generated `paw` and `domain-cli` skills MUST describe the current boundary-contract pattern and MUST fail drift checks when the guidance no longer matches the CLI source.
- **FR-013**: The CLI MUST stay Bun-first for runtime behavior and MUST NOT introduce a Node-specific runtime requirement as part of this feature.
- **FR-014**: The feature MUST evaluate locally vendored Effect v4 source before selecting any additional Effect package family for CLI use.
- **FR-015**: Additional Effect package families MUST be adopted only when they directly support a CLI boundary need in this feature.
- **FR-016**: Stream-oriented encoding support MUST remain out of scope until a command actually exposes streaming records.
- **FR-017**: The feature MUST NOT change frontend behavior, frontend gates, backend API behavior, or old Python CLI removal scope.

### Key Entities

- **CLI Boundary Contract**: A declared public shape for data entering or leaving the CLI.
- **Structured Command Output**: Machine-readable command result data printed to stdout.
- **Structured Error Output**: Machine-readable expected error data printed to stderr.
- **Config Source Summary**: The user-visible explanation of which source supplied each active setting.
- **Active Context**: The resolved profile, state roots, backend target, auth state, and source metadata for the current invocation.
- **Health Report**: The health command's aggregate status and named diagnostic checks.
- **Boundary Guidance Skill**: Generated agent guidance that teaches how to extend the CLI without bypassing shared contracts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of existing structured CLI outputs in the first CLI slice are validated or encoded through declared public contracts.
- **SC-002**: 100% of config-file reads in the first CLI slice reject wrong-shaped values with a config error that names the source.
- **SC-003**: Active-context tests cover at least five precedence combinations and prove the reported source matches the resolved value.
- **SC-004**: Expected structured error output contains the same required fields across usage and config failures.
- **SC-005**: A future command fixture that returns structured data outside its declared contract fails verification before it can be treated as supported behavior.
- **SC-006**: Generated `domain-cli` guidance contains the schema/config boundary pattern and the skill drift check fails when that guidance is stale.
- **SC-007**: The focused CLI verification gate completes without frontend checks and without requiring a running backend service.
- **SC-008**: The feature adds no auth secrets, tokens, cookies, or API keys to CLI config files or generated guidance.
- **SC-009**: Review of the selected Effect package families shows each added package has a direct CLI boundary use in this feature.

## Assumptions

- The current first-slice CLI package from `004-effect-paw-cli` remains the foundation and should be hardened rather than redesigned again.
- The local Effect v4 source under `backend/vendor/effect-smol` is the API truth for planning and implementation.
- The current CLI remains Bun-first and source-run for this feature.
- The useful scope is boundary-first: external inputs, public outputs, public expected errors, and generated guidance. Internal helper values that never cross a trust or public contract boundary do not need schema validation solely for ceremony.
- Stream encoders are deferred because the first CLI slice emits single command documents, not streaming records.
- Specs are local Pawrrtal planning artifacts under gitignored `specs/` unless explicitly force-added later.

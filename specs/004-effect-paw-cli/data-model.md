# Data Model: Effect Paw CLI

## CLI Package

Represents the standalone `@pawrrtal/cli` package.

**Fields**

- `name`: package name, fixed to `@pawrrtal/cli`.
- `path`: package directory, fixed to `packages/paw-cli`.
- `version`: package version shown by `paw --version`.
- `typescriptVersion`: canonical TypeScript major version, fixed to 6.x or newer for this feature.
- `rootCommand`: root Effect command exported from `src/Cli.ts`.
- `commandGroups`: list of registered feature-owned command groups.
- `skillProviders`: generated skill fragment providers for `paw` and `domain-cli`.

**Validation Rules**

- Must not import or execute `backend/app/cli/paw`.
- Must not depend on `frontend/`.
- Must expose package-local `check`, `typecheck`, and `test` scripts.
- Must keep TypeScript 6.x `typecheck` as the required compiler gate.
- May expose `typecheck:tsgo` only as an optional comparison gate.
- Source layout follows `src/Main.ts`, `src/Cli.ts`, `src/Commands.ts`, `src/Helpers/`, `src/Infrastructure/`, and `src/Modules/<Name>/Command.ts`.

## Command Metadata

Lightweight descriptive data exported beside an Effect command module. It feeds generated skills, contract tests, and completion generation, but it does not generate the runtime command tree.

**Fields**

- `name`: canonical command or group name.
- `summary`: short help text.
- `description`: long help text.
- `aliases`: documented aliases.
- `arguments`: positional inputs.
- `flags`: named options.
- `subcommands`: nested metadata rows for documentation and completion output.
- `examples`: runnable examples.
- `environment`: environment variables that affect this command.
- `outputModes`: supported output modes.
- `inputSources`: accepted body/document input sources.
- `exitCodes`: expected exit code categories.
- `owner`: package or feature that owns the command.
- `skillSections`: text or references used for generated skills.

**Validation Rules**

- `name` must be unique within sibling commands.
- Aliases must not conflict with canonical names.
- Resource command groups use noun names; subcommands use verb names.
- Descriptions used in Effect command help and skills must share the same source wording.
- Commands that support `--json` and `--plain` must declare their output schemas.
- Runtime behavior remains owned by the Effect command module.

## Command Group

Feature-owned collection of related Effect commands and their module-owned metadata.

**Fields**

- `name`: noun command group, such as `projects` in a later feature.
- `owner`: owning feature or package.
- `commands`: verb subcommands owned by the same module area.
- `registration`: package-local registration point.
- `skillContribution`: whether it contributes to `paw`, `domain-cli`, or both.

**Validation Rules**

- Must be independently testable.
- Must not require edits to unrelated command groups.
- Must not exist as a placeholder for a future feature that has no CLI workflow yet.

## Output Mode

Defines how a command reports results.

**Fields**

- `human`: default readable text.
- `json`: structured machine-readable output.
- `plain`: tab-separated output without headers.
- `stderrPolicy`: what progress, warnings, prompts, and errors may write.

**Validation Rules**

- `json` and `plain` are mutually exclusive.
- Parseable data goes to stdout.
- Warnings and errors go to stderr.
- Failed JSON-capable commands emit either a structured error object or no parseable payload; never mixed prose in stdout.

## CLI Error

Expected error category that maps to exit behavior.

**Fields**

- `kind`: `usage`, `config`, `auth`, `external`, `verification`, or `unexpected`.
- `message`: concise human message.
- `hint`: optional next step.
- `details`: verbose diagnostics shown only with verbose mode.
- `exitCode`: numeric exit code.

**Validation Rules**

- Default error output must be short and actionable.
- Verbose mode may include source chains and diagnostics.
- Exit code must match the contract in `contracts/cli-contract.md`.

## Health Report

Result of `paw doctor`.

**Fields**

- `checks`: list of `Health Check` rows.
- `summary`: counts of passed, warning, and failed checks.
- `context`: active profile/workspace/backend target used while checking.
- `staleness`: optional cache/discovery status.

**Validation Rules**

- Warning states must be represented separately from failures.
- A completed health command with warnings exits successfully unless a check is marked blocking.
- Failed blocking checks include a next step.

## Health Check

One diagnostic row inside a health report.

**Fields**

- `name`: stable machine-readable check name.
- `label`: human label.
- `state`: `pass`, `warn`, or `fail`.
- `message`: short result.
- `nextStep`: optional fix.
- `blocking`: whether failure should make `doctor` fail.

**Validation Rules**

- `name` is stable for scripts.
- `state` must be one of `pass`, `warn`, `fail`.
- `fail` requires `nextStep`.

## Active Context

The operator context that affects command behavior.

**Fields**

- `profile`: active profile name.
- `workspace`: active workspace or unset reason.
- `backendTarget`: resolved backend URL or local target.
- `configSources`: ordered sources used to resolve values.
- `authState`: known authenticated, unauthenticated, unknown, or not applicable.

**Validation Rules**

- `paw context` must be available without feature-specific command groups.
- Machine-readable context output must not include secret values.
- Config source order must be visible in verbose or structured output.

## Input Source Policy

Rules for commands that accept body, document, or bulk content.

**Fields**

- `flag`: explicit inline value, such as `--content`.
- `file`: path value or `-` for stdin.
- `stdin`: piped content.
- `editor`: interactive editor fallback.
- `allowedCombinations`: valid source combinations.

**Validation Rules**

- At most one body source may be supplied for a single input.
- Editor fallback only runs in an interactive terminal.
- Non-interactive callers receive an explicit validation error with an alternative.

## Generated Skill

`SKILL.md` output produced by `packages/ci/skill-gen/`.

**Fields**

- `name`: `paw` or `domain-cli`.
- `description`: skill frontmatter description.
- `sources`: module-owned metadata, dynamic fragments, or static source fragments that generated the skill.
- `body`: merged skill text.
- `outputPath`: `.agent/skills/<name>/SKILL.md`.

**Validation Rules**

- Must include the `AUTO-GENERATED by skill-gen` header.
- Must fail `skill-gen:check` when command metadata, skill fragments, or extension rules change.
- `paw` documents how to use the CLI.
- `domain-cli` documents how to change and test the CLI package.
- `domain-cli` must not keep permanent instructions for removing the old Python CLI after the one-time cleanup is complete.

## Retired Python CLI Surface

Old runtime paths that must be removed or rewritten.

**Fields**

- `pythonCommandPackage`: `backend/app/cli/paw/`.
- `pythonTests`: `backend/tests/paw/` and `backend/tests/e2e_paw/`.
- `consoleScript`: `backend/pyproject.toml` `paw = ...`.
- `launcher`: `scripts/paw`.
- `generatedSkills`: old `paw` and `paw-extend` fragments sourced from Python files.

**Validation Rules**

- Supported `paw` invocation must not execute Python CLI code.
- No generated skill may cite deleted Python CLI source files.
- Removed tests are replaced by package-local CLI tests for the new contract.

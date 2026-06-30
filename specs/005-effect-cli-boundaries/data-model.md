# Data Model: Effect CLI Boundaries

## CLI Boundary Contract

Represents a declared shape for data crossing a trust or public contract boundary.

**Fields**

- `name`: stable contract name.
- `owner`: CLI source area that owns the contract.
- `schema`: Effect Schema value used for decode and encode.
- `boundary`: one of `config-input`, `env-input`, `package-input`, `structured-output`, `structured-error`, or `skill-metadata`.

**Validation Rules**

- Every structured output and structured error contract must have an encoder path.
- Every unknown input contract must have a decoder path.
- Internal helper values that never cross a boundary do not need a contract.

## Active Context

Represents the context shown by `paw context` and injected into commands.

**Fields**

- `profile`: validated non-empty profile segment.
- `configRoot`: absolute config root path.
- `cacheRoot`: absolute cache root path.
- `backendTarget`: backend URL or `null`.
- `backendTargetSource`: source label or `null`.
- `backendTargetUnsetReason`: explanation when `backendTarget` is absent.
- `authState`: `not_applicable`, `unknown`, `authenticated`, or `unauthenticated`.
- `configSources`: ordered list of config source summaries.

**Validation Rules**

- Profile must match the existing safe profile-name policy.
- Secret values must never appear in source summaries.
- Empty source values are treated as unset before the active context is built.

## Config Source Summary

Represents source provenance for one resolved active-context value.

**Fields**

- `key`: public setting key.
- `source`: source label, such as `flag`, `env:PAW_PROFILE`, `project:<path>`, `profile:<path>`, `user:<path>`, `env:PAW_HOME`, `home-default`, or `unset`.
- `value`: non-secret display value or `null`.

**Validation Rules**

- `source` is always present.
- `value` is `null` when unset or intentionally hidden.

## TOML CLI Config

Represents decoded project, user, or profile TOML input.

**Fields**

- `profile`: optional profile name.
- `backendUrl`: optional backend target, decoded from `backend_url` or `backendUrl`.

**Validation Rules**

- Unknown top-level keys are tolerated unless they look secret-like.
- Supported keys must have string values after TOML parsing.
- Empty strings are treated as unset.
- Persisted profile config must reject secret-like keys before write.

## Environment Overrides

Represents decoded environment-backed CLI overrides.

**Fields**

- `pawHome`: optional state root override from `PAW_HOME`.
- `pawProfile`: optional profile override from `PAW_PROFILE`.
- `pawBackendUrl`: optional backend target override from `PAW_BACKEND_URL`.
- `xdgConfigHome`: optional config-root base from `XDG_CONFIG_HOME`.
- `xdgCacheHome`: optional cache-root base from `XDG_CACHE_HOME`.

**Validation Rules**

- Values are read through an Effect config descriptor against a supplied provider.
- Empty strings are treated as unset.
- Tests provide env through a deterministic provider rather than mutating the real environment.

## Health Report

Represents the structured `paw doctor` result.

**Fields**

- `status`: aggregate `pass`, `warn`, or `fail`.
- `checks`: ordered list of health checks.

**Validation Rules**

- Aggregate status is `fail` when any check fails, `warn` when no checks fail and at least one warns, otherwise `pass`.
- `checks` must not be empty.

## Health Check

Represents one named doctor diagnostic.

**Fields**

- `name`: stable check identifier.
- `status`: `pass`, `warn`, or `fail`.
- `detail`: human-readable explanation.

**Validation Rules**

- `name` and `detail` are non-empty.
- Check names are stable enough for automation tests.

## Structured CLI Error

Represents public structured error output and the shared expected error fields.

**Fields**

- `kind`: `usage`, `config`, `auth`, `external`, `verification`, or `unexpected`.
- `message`: required public error message.
- `hint`: optional recovery hint, encoded as `null` when absent in JSON.
- `details`: optional verbose details, encoded as `null` unless verbose diagnostics are requested.

**Validation Rules**

- Expected error classes are schema-backed tagged errors.
- Exit-code mapping remains based on the tagged error category.
- Verbose details must not appear in default human or structured output.

## Package Manifest Summary

Represents the minimum package metadata needed by the CLI.

**Fields**

- `version`: package version string.

**Validation Rules**

- Missing or non-string `version` is a local CLI failure.
- Version lookup has one source of truth for root `--version` and doctor.

## Command Metadata

Represents command metadata consumed by help, completions, tests, and generated skills.

**Fields**

- `name`, `summary`, `description`, `owner`.
- Optional `aliases`, `arguments`, `flags`, `examples`, `environment`, `notes`, `outputModes`, `exitCodes`, `subcommands`, and `inputSources`.

**Validation Rules**

- Command names and aliases must remain conflict-free.
- Metadata used by generated skills is validated before fragments are emitted.
- Help and generated skills must not bypass command metadata for duplicated wording.

## Boundary Guidance Fragment

Represents generated skill guidance teaching the CLI boundary pattern.

**Fields**

- Operational guidance for using current CLI output/config/error behavior.
- Domain guidance for adding schemas, config descriptors, structured output contracts, and tests.

**Validation Rules**

- Generated through `packages/ci/skill-gen/`.
- Drift check fails when the generated guidance is stale.
- Must not recommend Node runtime wiring or manual parsing/stringification for new boundaries.

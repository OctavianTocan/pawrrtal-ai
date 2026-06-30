# Research: Effect CLI Boundaries

## Decision: Keep the CLI on the explicit Effect v4 beta line

**Decision**: Keep `effect`, `@effect/platform-bun`, and `@effect/vitest` aligned on `4.0.0-beta.92` unless a newer `4.0.0-beta.*` is verified during implementation.

**Rationale**: `packages/paw-cli/package.json` already uses `4.0.0-beta.92`, `backend/vendor/effect-smol/packages/effect/package.json` is `4.0.0-beta.92`, and npm version metadata shows `4.0.0-beta.92` as the highest visible v4 beta. Npm's default `latest` tag is v3, so blindly using `latest` would downgrade away from the desired v4 line.

**Alternatives considered**:

- Use npm `latest`: rejected because it resolves to v3.
- Use snapshots: rejected because this repo has a vendored beta source and stable beta package pins.
- File-link `backend/vendor/effect-smol`: rejected because the domain-effect skill warns that the vendor workspace contains internal references.

## Decision: Schema belongs at CLI trust and public-contract boundaries

**Decision**: Use Effect `Schema` for unknown config-file data, package metadata, public command output, public error JSON, and command metadata consumed by generated skills.

**Rationale**: Current CLI code parses TOML as `unknown`, hand-walks records, directly stringifies output, and uses unvalidated plain objects for generated skill metadata. Effect v4 provides `Schema.decodeUnknownEffect`, `Schema.encodeUnknownEffect`, `Schema.Class`, `Schema.Struct`, and `Schema.TaggedErrorClass`, matching the backend-ts convention that public domain shapes are schema-backed.

**Alternatives considered**:

- Validate every internal helper value: rejected as ceremony outside trust/public boundaries.
- Keep manual guards: rejected because config/output/error drift is the core problem.
- Add a separate schema package: rejected because the CLI package is small and current ownership boundaries are clear.

## Decision: Use `Schema.Class` for public result/error entities and `Schema.Struct` for intermediate decode shapes

**Decision**: Use `Schema.Class` for exported public CLI result entities and schema-backed errors. Use `Schema.Struct` for intermediate decoded config and package metadata where class construction adds no value.

**Rationale**: This follows `backend-ts/CONVENTIONS.md`: public domain entities and errors are concrete schema-backed data, while small input decoder shapes can stay structural. It also avoids forcing every config helper into class instances.

**Alternatives considered**:

- Use only `Schema.Struct`: rejected for public entities because backend-ts establishes `Schema.Class` as the richer public-domain pattern.
- Use only `Schema.Class`: rejected for intermediate TOML/package decode shapes because it increases object churn without user value.

## Decision: Convert expected CLI failures to schema-backed tagged errors

**Decision**: Replace public expected CLI errors with `Schema.TaggedErrorClass` and keep the existing public error categories and exit-code mapping.

**Rationale**: Current `Data.TaggedError` classes are typed but not schema-backed. The CLI error surface is part of the public contract for agents and automation, so its structured output should encode from the same declared shape as its typed failures.

**Alternatives considered**:

- Keep `Data.TaggedError`: rejected because it does not solve structured error drift.
- Collapse errors into one generic class: rejected because current exit-code categories are useful and already documented.

## Decision: Use Effect `Config` for provider-backed env descriptors, not for the whole precedence engine

**Decision**: Define env descriptor configs with `Config.*` and parse them against `ConfigProvider.fromEnv({ env })` in the CLI's existing process/env test seam. Keep Paw's explicit precedence resolver for flags, env, project TOML, profile TOML, user TOML, and defaults.

**Rationale**: Effect `Config` is excellent for typed provider-backed lookups and deterministic tests. Paw's precedence is a domain policy that combines CLI flags and multiple TOML files with source labels, so replacing it wholesale with provider fallback composition would obscure the source-reporting contract.

**Alternatives considered**:

- Replace all config resolution with nested `ConfigProvider.orElse`: rejected because source labels and flag precedence become harder to audit.
- Keep raw env reads only: rejected because tests need deterministic provider-backed config and env value decoding.

## Decision: Keep Bun platform services as the runtime boundary

**Decision**: Keep `@effect/platform-bun` and `BunRuntime.runMain`; do not introduce `@effect/platform-node` or `node:*` imports in CLI source.

**Rationale**: The CLI package was explicitly scoped as Bun-first. `backend/vendor/effect-smol/packages/platform-bun` provides Bun-backed services including filesystem, path, stdio, terminal, child process spawning, and runtime wiring.

**Alternatives considered**:

- Follow older docs that show `@effect/platform-node`: rejected because they conflict with the requested Bun runtime.
- Build a dual Node/Bun runtime now: rejected because external distribution is not in this feature.

## Decision: Defer `effect/unstable/encoding`

**Decision**: Do not use `effect/unstable/encoding` in this feature.

**Rationale**: The available encoding package is useful for schema-aware NDJSON/SSE/message-pack streams, but the current CLI emits single JSON documents for `context`, `doctor`, and structured errors. Schema encode plus `JSON.stringify` after encoding is the right first step.

**Alternatives considered**:

- Adopt NDJSON helpers now: rejected because no current command streams records.
- Ban the package permanently: rejected because later bulk/watch commands may need it.

## Decision: Generated skills must teach the new boundary pattern

**Decision**: Update `packages/paw-cli/src/Skills/Fragments.ts` so generated `domain-cli` guidance tells agents to add schemas, config descriptors, structured output contracts, and tests before adding ad hoc parsing/rendering.

**Rationale**: Pawrrtal uses generated skills as agent continuity. If the skill continues to teach `Helpers/Config.ts` and `Helpers/Output.ts` without the schema/config-first rule, future commands will copy the old weak pattern.

**Alternatives considered**:

- Leave skills for a later docs pass: rejected because skill drift is part of the feature's success criteria.
- Hand-edit `.agent/skills/domain-cli/SKILL.md`: rejected because generated skills must come from `skill-gen`.

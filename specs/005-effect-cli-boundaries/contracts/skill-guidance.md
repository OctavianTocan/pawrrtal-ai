# Contract: Generated CLI Skill Guidance

## Generated Skills

The feature updates generated guidance for:

| Skill | Purpose |
| --- | --- |
| `paw` | Teaches agents how to use the supported CLI surface. |
| `domain-cli` | Teaches agents how to change, extend, test, and review `packages/paw-cli`. |

Both skills remain generated through `packages/ci/skill-gen/`.

## Required `domain-cli` Boundary Guidance

The generated `domain-cli` skill must instruct future agents to:

- Keep `effect`, `@effect/platform-bun`, and `@effect/vitest` aligned on the latest verified v4 beta line.
- Use Bun runtime services and avoid Node-specific runtime imports in CLI source.
- Define schemas for untrusted input and public output before adding ad hoc parsing or rendering.
- Use `Schema.TaggedErrorClass` for expected public CLI failures.
- Use Effect `Config` descriptors and deterministic `ConfigProvider` tests for environment-backed settings.
- Preserve explicit Paw config precedence and source labels.
- Encode structured output and structured errors through declared schemas.
- Update command metadata and generated skill fragments from the real command surface.

## Required `paw` Usage Guidance

The generated operational `paw` skill must explain:

- Which commands support structured output.
- That structured stdout is schema-validated command data only.
- That expected errors are rendered separately on stderr.
- How config source labels appear in `paw context`.
- Which gates verify boundary contract drift.

## Drift Rules

`bun run skill-gen:check` must fail when:

- Generated skills still teach manual TOML record walking as the preferred pattern.
- Generated skills still teach direct JSON stringification as the preferred structured-output pattern.
- Generated skills recommend Node runtime wiring for the Bun-first CLI.
- Generated skills omit the schema/config-first command-extension rule.
- Generated command metadata no longer matches the real command registry.

## Non-Goals

- Do not hand-edit generated `SKILL.md` files to satisfy this contract.
- Do not introduce a separate CLI-only skill generator.
- Do not document future commands that are not exposed by the real command registry.

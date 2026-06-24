# Config — module-scoped env reads

Effect v4 pattern for reading environment variables in `apps/api`. Translate v3 layout examples from the architecture reference vendor; API surface comes from `effect-smol`.

## Where config lives

| Put it here | Not here |
|---|---|
| `apps/api/src/Modules/<Feature>/Config.ts` | `Infrastructure/` |
| Yieldable `Config` export (e.g. `AllowedEmailsConfig`) | `Context.Service` / `Context.Tag` |
| Pure parser tested without Effect | `packages/api-core` (no env reads) |

**Infrastructure config** (`Infrastructure/Database/Config.ts`) exists only because `SqliteClient.layerConfig` demands `Config.Wrap`. That is client wiring, not feature policy.

**Module-scoped config** — domain env vars live with the feature module:

- `backend/vendor/effect-api-layout/apps/api/src/Modules/Authentication/Config.ts` — `AuthConfig`
- `backend/vendor/effect-api-layout/packages/*/sandbox/src/Config.ts` — `SandboxConfig` (`withDefault` + `mapOrFail`)
- `backend/vendor/effect-api-layout/apps/api/src/Modules/Integrations/Providers/Slack/Config.ts` — provider env bundle

## What to export

Yieldable `Config` value — not a `Context.Tag`:

```ts
// apps/api/src/Modules/<Feature>/Config.ts

export const AllowedEmailsConfig = Config.string('ALLOWED_EMAILS').pipe(
  Config.withDefault(''),
  Config.map(parseAllowedEmails)
);
```

Export the pure parser separately for unit tests without `ConfigProvider` (same split as `parseRivetEndpoint` vs `RivetEndpointConfig` in the architecture reference).

## Combinator choice (v4 / effect-smol)

| Need | Use | Not |
|------|-----|-----|
| Transform string → set, lowercase | `Config.map` | `Config.array` (Python comma-splits a string) |
| Validate enum / fail loud | `Config.mapOrFail` | `Config.map` |
| Multi-key struct | `Config.schema(Schema.Struct(...))` | Hand-rolled Tag |
| Missing env with default | `Config.withDefault('')` | `Context.Service` |
| Library client layer | `Config.Wrap` + `layerConfig` | Plain `Config` in middleware |

`withDefault` only applies when data is **missing**; wrong types still fail.

## Wiring

In `Layer.effect` for the consumer (middleware, service):

```ts
const allowedEmails = yield* AllowedEmailsConfig;
// closure captures `allowedEmails` for the middleware function
```

- Read once at layer construction.
- No `layerConfig` for middleware — that is for `SqliteClient`, `BunHttpServer`, etc.
- Provide the **middleware layer** on `Http*Live`, not a separate config service layer.

## Anti-patterns

| Don't | Do |
|-------|-----|
| `Infrastructure/Config/` for feature env | `Modules/<Feature>/Config.ts` |
| `Context.Service` for one consumer | `yield* Config` in `Layer.effect` |
| Copy v3 `@effect/platform` imports | Translate against `effect-smol` |
| Use `Database/Config.ts` as the template | Use module `Config.ts` examples above |

## Architecture reference paths

| Path | Extract |
|------|---------|
| `effect-api-layout/apps/api/src/Modules/Authentication/Config.ts` | `Config.all`, yield in layer |
| `effect-api-layout/apps/api/test/unit/Modules/Authentication/Config.test.ts` | `ConfigProvider.fromMap` |
| `effect-api-layout/packages/*/sandbox/src/Config.ts` | `withDefault` + `mapOrFail` |
| `effect-smol/packages/effect/src/Config.ts` | v4 `string`, `withDefault`, `map` |

## Pawrrtal live

| Path | Notes |
|------|-------|
| `backend-ts/apps/api/src/Infrastructure/Database/Config.ts` | `Config.Wrap` for SQLite only |
| `backend-ts/apps/api/src/Modules/Authentication/Config.ts` | Allowlist (Lesson 6) |

## Python parity (allowlist)

`backend/app/infrastructure/config.py:147-163` — comma-split, strip, lower; empty string → open deployment.

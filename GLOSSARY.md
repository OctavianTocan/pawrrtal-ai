# Effect-TS + Pawrrtal Auth Glossary

Vocabulary for the Effect-TS auth migration arc (Lessons 1-5+). Every
lesson and learning record adheres to these terms. New terms land here
only after the user can use them correctly.

## Effect v4 service kernel

**`Context.Service<Identity, Interface>()('id')`**
: v4 class-form service definition. The class identity doubles as the
type-level tag; the second type parameter is the *bare* interface
(not an object literal). Identifier is a string in the form
`'@apps/api/<Name>'`.
_Avoid_: `Context.Tag<…>()` (v3), `Context.Reference<…>()` (config, not
service).

**`yield* ServiceName`**
: The only verb for "consume a service from the Effect environment."
Returns the service's interface value.

**`Layer.succeed(Class, value)`**
: The simplest "this constant value IS the service" layer. Use for
hardcoded fixtures and tests.
_Avoid_: `Layer.succeedEffect` (returns an `Effect` — wrong verb;
`Layer.effect` is the body-yielding twin).

**`Layer.effect(Class, Effect.gen(...))`**
: The "build the service from an `Effect`" layer. The body can
`yield*` other services to declare dependencies.
_Avoid_: `Layer.succeed` when the body has dependencies — the R
channel will silently drop them.

**`Layer.provide(InnerLayer, [OuterLayer, ...])`**
: Satisfies `InnerLayer`'s R-channel by providing `OuterLayer`. Does
NOT expose the outer layer to the rest of the environment.
_Avoid_: `Layer.provideMerge` when the outer layer should be visible
to siblings — different verb, different scope.

**`Layer.provideMerge(InnerLayer, OuterLayer)`**
: Like `Layer.provide`, but also adds the outer layer to the merged
environment. Use when siblings need the same dependency the inner
layer consumed.

## Schema

**`Schema.Class<Name>('Name')({...fields})`**
: A schema that produces an *instance* of a class with the named
fields. Use for domain types that have behaviour. Construct with
`new User({...})`.
_Avoid_: `Schema.Struct` when the value is passed to typed code
that expects a class.

**`Schema.Struct({...})`**
: A plain object schema. Use for value-only payloads (request/response
bodies) that have no behaviour.

**`Schema.TaggedErrorClass<Name>('Name', {fields}, {httpApiStatus: N})`**
: An error class with a discriminator tag and an HTTP status code
for the `HttpApi` error channel. The third argument maps to status;
omit it for internal-only errors.
_Avoid_: `Schema.Class` for errors (no tag) or `Schema.Struct` (no
class identity).

## Effect combinators

**`Effect.gen(function*() { yield*; ...; return ... })`**
: The imperative `Effect` program. Use for service composition and
sequential logic. Never put `try`/`catch` inside.

**`Effect.fn('SpanName')(function*(args) {...})`**
: Like `Effect.gen` but a named, traced function. The first argument
becomes the OpenTelemetry span name. Use for any non-trivial
helper that other code calls.
_Avoid_: bare `Effect.gen` for anything that shows up in trace.

**`Effect.withSpan('name')`**
: Attach a span to an `Effect` without making it a function. Use in
`pipe` chains where the effect is constructed inline.
_Avoid_: `Effect.tap` for trace attachment (different verb, different
intent).

**`Effect.provideService(effect, Class, value)`**
: Inject a service value into an `Effect`'s environment. The
canonical place in `HttpApiMiddleware` bodies — provides
`CurrentUser` to the downstream `httpEffect`.
_Avoid_: `Effect.provide` for a single service (that's the
`Layer`-level verb).

## HttpApi (v4)

**`HttpApiMiddleware.Service<Identity>()('name', { provides, error, security })`**
: The contract class for a middleware. `provides` is the service it
injects; `error` is the typed error it may raise; `security` is the
record of credential schemes clients must supply.
_Avoid_: v3 `HttpApiMiddleware.Tag<…>(…{ failure, ... })` — `failure`
was renamed to `error` in v4.

**`HttpApiSecurity.apiKey({ key, in: 'cookie' | 'header' | 'query' })`**
: A credential scheme for values passed in cookies, headers, or
query strings. The credential arrives in the body as
`Redacted<string>` — unwrap with `Redacted.value(credential)`.
_Avoid_: `HttpApiSecurity.bearer` when the credential is a cookie,
not an `Authorization: Bearer …` header.

**`HttpApiBuilder.group(Api, 'name', Effect.fn(handlers => ...))`**
: Wire an `HttpApiGroup` to its handlers. Middleware attaches via
`.middleware(AuthClass)` on the *group*, not on the root `Api`.
_Avoid_: attaching middleware at the `Api` level for a single group
(over-applies to `system`, `health`, etc.).

**`requiredForClient: true`**
: Config flag on `HttpApiMiddleware.Service` that requires the
generated client to also supply the security credentials. Default
`false`.
_Avoid_: leaving it `false` for production auth — the client will
silently omit the cookie.

## I/O at the trust boundary

**Trust boundary**
: The line between data you wrote (your DB, your service's
in-memory state) and data you didn't (HTTP from another process,
file contents from disk, user input). Schema-decode at this line;
direct-construct + cast only on the trusted side on a sync path.
_Avoid_: "cast everything" (hides malformed data); "decode
everywhere" (the sync decoder can't satisfy
`DecodingServices` on its own — fights the type system).

**`HttpClientResponse.schemaBodyJson(Schema)`**
: The one-call "fetch JSON and decode it through this schema" helper.
For a plain `Schema.Class`, `DecodingServices` is `never` — no
service to provide, no cast, no R-channel pain. If it ever shows
`unknown`, the schema didn't infer as the class; investigate,
don't cast.
_Avoid_: `response.json` + `Schema.decodeUnknown(...)` + `Effect.try`
+ cast — re-implements the helper with worse types.

## Type identity

**`UserId`**
: A branded `Schema.String` for user IDs. Built once in
`packages/api-core/src/Lib/TypeIds.ts:19`. Use the brand everywhere
a `UserId` is required; do not pass raw strings.
_Avoid_: re-declaring `UserId` per-module (drift).

**`'@apps/api/<Name>'`**
: The Pawrrtal identifier form for `Context.Service` and
`HttpApiMiddleware.Service` instances. Matches comcom's
`'<scope>/<pkg>/<Module>'` rule. Locked in LR-0007.
_Avoid_: bare v4 form (`"acme/HttpApi/Authorization"`); npm-scope
form (`'@pawrrtal/api/...'`).

## Layer naming

**`Test` layer**
: The hardcoded fixture layer, attached as a `static readonly` on
the service class. Used by scratchpads, unit tests, dev tooling.
_Not_ the production implementation.

**`Live` layer**
: The runtime layer that talks to real I/O. Lands in `apps/api/...`,
not in `api-core` (api-core is contract-only).
_Avoid_: comcom's `Default`; smol's generic `layer` — Pawrrtal
pinned to `Live` (per LR-0002).

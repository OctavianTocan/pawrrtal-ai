# Api-Core Contract Pattern

Use this when a lesson asks you to add a new `backend-ts/packages/api-core`
module before writing runtime handlers.

## Rule

`api-core` describes the wire contract only:

1. `Domain.ts` names request and response schemas.
2. `Errors.ts` names typed HTTP failures.
3. `Api.ts` maps methods, paths, params, payloads, success shapes, errors,
   auth middleware, and the group prefix.
4. Root `Api.ts` registers the group.

Do not import runtime services, SQL, repositories, or Python code into
`api-core`.

## Shape

| File | Pattern to mirror | What changes |
|---|---|---|
| `Modules/Projects/Domain.ts` | `Schema.Class` response/input classes | Replace fields with the new endpoint schemas |
| `Modules/Projects/Errors.ts` | `Schema.TaggedErrorClass` + `httpApiStatus` | Add only errors the HTTP contract returns |
| `Modules/Projects/Api.ts` | `HttpApiGroup.make(...).add(...).middleware(...).prefix(...)` | Add endpoints and route-specific schemas |
| `Api.ts` | `.add(ProjectsApi)` | Add the new group once |

## Middleware Order

Protected groups use the same two middlewares:

1. `AllowedUserMiddlewareService`
2. `AuthenticationMiddlewareService`

The last `.middleware(...)` is outermost, so authentication runs first and
provides `CurrentUser`; allowlist then reads `CurrentUser`.

## Endpoint Mapping Checklist

For each Python route, write down:

| Question | Example |
|---|---|
| What is the HTTP method? | `GET` |
| What is the path under the group prefix? | `/:conversation_id/messages` |
| Are there params? | `{ conversation_id: ConversationId }` |
| Is there a JSON payload? | `ConversationUpdateInput` |
| What is the success schema? | `Conversation` or `Schema.Array(ChatMessageRead)` |
| What failures are part of the contract? | `ConversationNotFoundError` |
| Is Python behavior unusual? | `GET /:id` returns `null`, not 404 |

## Common Mistakes

- Do not copy runtime validation guards into `Api.ts`. Put field constraints in
  `Domain.ts` when they are part of request parsing.
- Do not create a generic `NotFoundError` if the existing module pattern uses a
  feature-specific error class.
- Do not silently "improve" Python parity in the contract. If Python returns
  `null`, model `null`; fix behavior in a later parity lesson only if the lesson
  says to.
- Do not add handler code while working in `packages/api-core`.

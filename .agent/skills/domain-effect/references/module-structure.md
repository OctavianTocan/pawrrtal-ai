# Module Structure

Use the current `backend-ts` layout, not comcom package paths.

```text
backend-ts/
├── packages/api-core/src/
│   ├── Api.ts                 root HttpApi assembly
│   └── Modules/<Name>/
│       ├── Api.ts             HttpApi group and endpoints
│       ├── Domain.ts          schemas, ids, readonly domain values
│       └── Errors.ts          public tagged errors
└── apps/api/src/
    ├── App.ts                 app assembly
    ├── Main.ts                runtime entrypoint
    ├── Infrastructure/        database, env, platform services
    └── Modules/<Name>/
        ├── Http.ts            handler wiring
        ├── Service.ts         business rules
        ├── Repo.ts            persistence
        └── Policy.ts          authz and request policy
```

## File Roles

- `Domain.ts`: `Schema.Class`, ids, branded values, request/response shapes.
- `Errors.ts`: `Schema.TaggedError` values that are part of the public contract.
- `Api.ts`: endpoint declarations only.
- `Http.ts`: request boundary only. No state, no caches, no timers.
- `Service.ts`: business behavior and dependency use.
- `Repo.ts`: SQL/storage. Keep database row details here.
- `Policy.ts`: authz checks that are not pure schema validation.

Promote a helper to its own file only when it has a real name and multiple
callers. Do not create empty `Config.ts`, `Events.ts`, or `Helpers.ts` files
just because another module has them.

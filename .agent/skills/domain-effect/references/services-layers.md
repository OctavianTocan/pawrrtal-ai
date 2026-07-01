# Services And Layers

Default to `Effect.Service` for application services in `backend-ts/apps/api`.
Declare every production dependency in the `dependencies` array so
`Service.Default` is fully wired for runtime use and
`Service.DefaultWithoutDependencies` stays available for tests.

```ts
export class ProjectsService extends Effect.Service<ProjectsService>()(
  '@pawrrtal/api/Projects/Service',
  {
    dependencies: [ProjectsRepo.Default],
    effect: Effect.gen(function* () {
      const repo = yield* ProjectsRepo

      return {
        list: Effect.fn('ProjectsService.list')(function* (userId: UserId) {
          return yield* repo.listByUser(userId)
        }),
      }
    }),
  }
) {}
```

## Rules

- Use service identifiers that match package ownership:
  `@pawrrtal/api/<Module>/<Role>` or `@pawrrtal/api-core/<Module>/<Role>`.
- Use `scoped:` instead of `effect:` when constructing resources with
  finalizers, queues, forks, or acquire/release lifecycles.
- Use `Effect.fn('Service.method')` for service/repo/policy methods that deserve
  spans. Do not wrap the same method in `Effect.withSpan`.
- Use `Effect.fnUntraced` for inner helpers that should not create their own
  span.
- Keep `Http.ts` thin. Move business decisions into `Service.ts`.
- Use `Context.Tag` for externally injected resources, config bags, and test
  seams; use `Effect.Service` for app services with constructors.

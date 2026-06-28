import { Api } from "@pawrrtal/api-core"
import {
  Project,
  type ProjectCreateInput,
  type ProjectId,
  type ProjectUpdateInput,
  type UserId
} from "@pawrrtal/api-core/Modules/Projects/Domain"
import type { ProjectNotFoundError } from "@pawrrtal/api-core/Modules/Projects/Errors"
import { DateTime, Effect } from "effect"
import { HttpApiBuilder } from "effect/unstable/httpapi"

export const STUB_USER_ID = "00000000-0000-4000-8000-000000000001" as UserId
export const FAKE_PROJECT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d" as ProjectId
export const FAKE_DATE = DateTime.makeUnsafe("2026-06-08T12:00:00.000Z")

export type ProjectsTestClient = {
  readonly projects: {
    readonly list: () => Effect.Effect<ReadonlyArray<Project>>
    readonly create: (request: { readonly payload: ProjectCreateInput }) => Effect.Effect<Project>
    readonly update: (request: {
      readonly params: { readonly project_id: string }
      readonly payload: ProjectUpdateInput
    }) => Effect.Effect<Project>
    readonly delete: (request: { readonly params: { readonly project_id: string } }) => Effect.Effect<void>
  }
}

export const fakeProject = (overrides: Partial<{ name: string; id: string }> = {}): Project =>
  new Project({
    id: (overrides.id ?? FAKE_PROJECT_ID) as ProjectId,
    user_id: STUB_USER_ID,
    name: overrides.name ?? "fake",
    created_at: FAKE_DATE,
    updated_at: FAKE_DATE
  })

/** Build a handler layer for the projects API. */
export const makeHandlerLayer = (overrides: {
  list?: () => Effect.Effect<ReadonlyArray<Project>, never>
  create?: (name: string) => Effect.Effect<Project, never>
  update?: (id: string, name: string) => Effect.Effect<Project, ProjectNotFoundError>
  delete?: (id: string) => Effect.Effect<void, ProjectNotFoundError>
}) => {
  const defaults = {
    list: () => Effect.succeed<ReadonlyArray<Project>>([]),
    create: (name: string) => Effect.succeed(fakeProject({ name })),
    update: (id: string, name: string) => Effect.succeed(fakeProject({ id, name })),
    delete: () => Effect.void
  }
  const h = { ...defaults, ...overrides }

  return HttpApiBuilder.group(Api, "projects", (handlers) =>
    Effect.gen(function* () {
      return handlers
        .handle("list", () => h.list())
        .handle("create", ({ payload }) => h.create(payload.name))
        .handle("update", ({ params, payload }) => h.update(params.project_id, payload.name ?? "kept"))
        .handle("delete", ({ params }) => h.delete(params.project_id))
    })
  )
}

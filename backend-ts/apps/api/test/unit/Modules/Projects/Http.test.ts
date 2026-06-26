/** Projects HTTP wire-shape tests via `HttpApiTest.groups`. */

import { NodeHttpServer } from "@effect/platform-node"
import { assert } from "@effect/vitest"
import { Api } from "@pawrrtal/api-core"
import {
  Project,
  ProjectCreateInput,
  type ProjectId,
  ProjectUpdateInput,
  type UserId
} from "@pawrrtal/api-core/Modules/Projects/Domain"
import { ProjectNotFoundError } from "@pawrrtal/api-core/Modules/Projects/Errors"
import { DateTime, Effect, Exit, Layer } from "effect"
import { HttpApiBuilder, HttpApiTest } from "effect/unstable/httpapi"
import { describe, it } from "vitest"
import { AllowedUserMiddlewareStubLive, AuthMiddlewareStubLive } from "../../_helpers/AuthStub"

const STUB_USER_ID = "00000000-0000-4000-8000-000000000001" as UserId
const FAKE_PROJECT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d" as ProjectId
const FAKE_DATE = DateTime.makeUnsafe("2026-06-08T12:00:00.000Z")

type ProjectsTestClient = {
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

const fakeProject = (overrides: Partial<{ name: string; id: string }> = {}): Project =>
  new Project({
    id: overrides.id ?? FAKE_PROJECT_ID,
    user_id: STUB_USER_ID,
    name: overrides.name ?? "fake",
    created_at: FAKE_DATE,
    updated_at: FAKE_DATE
  })

describe("Projects.Http (handler stubs)", () => {
  const makeHandlerLayer = (overrides: {
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

  const platformLayer = NodeHttpServer.layerHttpServices

  const getClient = async (handlerLayer: ReturnType<typeof makeHandlerLayer>): Promise<ProjectsTestClient> =>
    Effect.runPromise(
      HttpApiTest.groups(Api, ["projects"]).pipe(
        Effect.scoped,
        Effect.provide([
          platformLayer,
          // Auth is a dependency of the handler layer (see `HttpProjectsLive`), not a sibling layer.
          handlerLayer.pipe(Layer.provide(Layer.mergeAll(AuthMiddlewareStubLive, AllowedUserMiddlewareStubLive)))
        ])
      ) as unknown as Effect.Effect<ProjectsTestClient, never, never>
    )

  it("GET /api/v1/projects returns 200 with the list", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([fakeProject({ name: "a" }), fakeProject({ name: "b" })])
    })
    const client = await getClient(handler)
    const list = await Effect.runPromise(client.projects.list())
    assert.strictEqual(list.length, 2)
    const first = list[0]
    assert.isDefined(first)
    assert.strictEqual(first.name, "a")
  })

  it("POST /api/v1/projects returns 201 with the new project", async () => {
    const handler = makeHandlerLayer({})
    const client = await getClient(handler)
    const created = await Effect.runPromise(
      client.projects.create({ payload: new ProjectCreateInput({ name: "fresh" }) })
    )
    assert.strictEqual(created.name, "fresh")
  })

  it("PATCH /api/v1/projects/:id returns 200 with the renamed project", async () => {
    const handler = makeHandlerLayer({})
    const client = await getClient(handler)
    const updated = await Effect.runPromise(
      client.projects.update({
        params: { project_id: FAKE_PROJECT_ID },
        payload: new ProjectUpdateInput({ name: "renamed" })
      })
    )
    assert.strictEqual(updated.name, "renamed")
  })

  it("PATCH on a missing project fails with ProjectNotFoundError", async () => {
    const handler = makeHandlerLayer({
      update: () => Effect.fail(new ProjectNotFoundError({ project_id: FAKE_PROJECT_ID }))
    })
    const client = await getClient(handler)
    const exit = await Effect.runPromise(
      client.projects
        .update({
          params: { project_id: FAKE_PROJECT_ID },
          payload: new ProjectUpdateInput({ name: "x" })
        })
        .pipe(Effect.exit)
    )
    assert.isTrue(Exit.isFailure(exit))
  })

  it("DELETE /api/v1/projects/:id returns 204 No Content", async () => {
    const handler = makeHandlerLayer({})
    const client = await getClient(handler)
    await Effect.runPromise(client.projects.delete({ params: { project_id: FAKE_PROJECT_ID } }))
  })

  it("DELETE on a missing project fails with ProjectNotFoundError", async () => {
    const handler = makeHandlerLayer({
      delete: () => Effect.fail(new ProjectNotFoundError({ project_id: FAKE_PROJECT_ID }))
    })
    const client = await getClient(handler)
    const exit = await Effect.runPromise(
      client.projects.delete({ params: { project_id: FAKE_PROJECT_ID } }).pipe(Effect.exit)
    )
    assert.isTrue(Exit.isFailure(exit))
  })
})

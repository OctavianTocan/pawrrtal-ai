import { NodeHttpServer } from "@effect/platform-node"
import { HttpAllowedUserLive } from "@pawrrtal/api/src/Modules/Authentication/Http"
import { Api } from "@pawrrtal/api-core"
import { AuthorizationError } from "@pawrrtal/api-core/Modules/Auth/Errors"
import { Cause, ConfigProvider, Effect, Exit, Layer } from "effect"
import { HttpApiTest } from "effect/unstable/httpapi"
import { assert, describe, it } from "vitest"
import { AuthMiddlewareStubLive } from "../../_helpers/AuthStub"
import type { ProjectsTestClient } from "../../_helpers/ProjectsStub"
import { fakeProject, makeHandlerLayer } from "../../_helpers/ProjectsStub"

describe("Authentication.AllowedUser", () => {
  const platformLayer = NodeHttpServer.layerHttpServices

  // Build a client for the handler layer.
  const getClient = async (
    handlerLayer: ReturnType<typeof makeHandlerLayer>,
    env: Record<string, string> = {}
  ): Promise<ProjectsTestClient> => {
    const provider = ConfigProvider.fromEnv({ env })
    return Effect.runPromise(
      HttpApiTest.groups(Api, ["projects"]).pipe(
        Effect.scoped,
        Effect.provide([
          platformLayer,
          handlerLayer.pipe(
            Layer.provide(
              Layer.mergeAll(AuthMiddlewareStubLive, HttpAllowedUserLive).pipe(
                Layer.provide(ConfigProvider.layer(provider))
              )
            )
          )
        ])
      ) as unknown as Effect.Effect<ProjectsTestClient, never, never>
    )
  }

  it("should return a 403 if the user is not allowed to access the resource", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([])
    })

    const client = await getClient(handler, { ALLOWED_EMAILS: "other@example.com" })

    const exit = await Effect.runPromise(client.projects.list().pipe(Effect.exit))
    assert.isTrue(Exit.isFailure(exit))
    if (Exit.isFailure(exit)) {
      const errors = exit.cause.reasons.filter(Cause.isFailReason).map((reason) => reason.error as any)
      assert.isTrue(errors.some((error) => error instanceof AuthorizationError))
      const authError = errors.find((error) => error instanceof AuthorizationError) as AuthorizationError
      assert.strictEqual(authError.message, "This Pawrrtal deployment is private.")
    }
  })

  it("should let everyone through if the allowlist is empty", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([fakeProject({ name: "y" })])
    })
    const client = await getClient(handler, { ALLOWED_EMAILS: "" })
    const list = await Effect.runPromise(client.projects.list())
    assert.strictEqual(list.length, 1)
    assert.strictEqual(list[0]?.name, "y")
  })

  it("should admit listed email case-insensitive", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([fakeProject({ name: "y" })])
    })
    const client = await getClient(handler, { ALLOWED_EMAILS: "Test@Example.com" })
    const list = await Effect.runPromise(client.projects.list())
    assert.strictEqual(list.length, 1)
    assert.strictEqual(list[0]?.name, "y")
  })

  it("should block unlisted email with a generic message", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([])
    })
    const client = await getClient(handler, { ALLOWED_EMAILS: "other@example.com" })
    const exit = await Effect.runPromise(client.projects.list().pipe(Effect.exit))
    assert.isTrue(Exit.isFailure(exit))
    if (Exit.isFailure(exit)) {
      const errors = exit.cause.reasons.filter(Cause.isFailReason).map((reason) => reason.error as any)
      const authError = errors.find((error) => error instanceof AuthorizationError) as AuthorizationError
      assert.isDefined(authError)
      assert.strictEqual(authError.message, "This Pawrrtal deployment is private.")
    }
  })

  it("should parse comma-separated values", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([fakeProject({ name: "y" })])
    })
    const client = await getClient(handler, { ALLOWED_EMAILS: "other@example.com, test@example.com" })
    const list = await Effect.runPromise(client.projects.list())
    assert.strictEqual(list.length, 1)
  })

  it("should be empty when unset", async () => {
    const handler = makeHandlerLayer({
      list: () => Effect.succeed([fakeProject({ name: "y" })])
    })
    const client = await getClient(handler, {})
    const list = await Effect.runPromise(client.projects.list())
    assert.strictEqual(list.length, 1)
  })
})

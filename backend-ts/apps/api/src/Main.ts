/** Effect v4 API entrypoint (strangler on :8001). */

import { BunHttpServer, BunRuntime } from "@effect/platform-bun"
import { Layer } from "effect"
import { HttpRouter } from "effect/unstable/http"
import { AppLive } from "./App"

const PORT = 8001

const HttpServerLayer = HttpRouter.serve(AppLive).pipe(Layer.provide(BunHttpServer.layer({ port: PORT })), Layer.orDie)

// Narrow R to `never` — HttpApiBuilder.group widens the layer R channel at the type level.
const HttpServerLayerClosed = HttpServerLayer as Layer.Layer<never, never, never>

Layer.launch(HttpServerLayerClosed).pipe(BunRuntime.runMain)

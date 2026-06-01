import { NodeHttpServer, NodeRuntime } from "@effect/platform-node"
import { Layer } from "effect"
import { createServer } from "node:http"
import { HttpRouter } from "effect/unstable/http"
import { AppLive } from "./App"

const PORT = 8001;

// Creates an HTTP server that serves the API routes.
const HttpServerLayer = HttpRouter.serve(AppLive).pipe(Layer.provide(NodeHttpServer.layer(createServer, { port: PORT })));

// Actually start the process.
Layer.launch(HttpServerLayer).pipe(NodeRuntime.runMain);

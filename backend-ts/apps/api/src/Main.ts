/**
 * Effect v4 API entrypoint (strangler on :8001).
 *
 *   HttpServerLayer = HttpRouter.serve(AppLive)
 *                       .pipe(Layer.provide(NodeHttpServer.layer(createServer, { port: 8001 })))
 *                       .pipe(Layer.orDie)
 *
 *   Layer.launch(HttpServerLayer).pipe(NodeRuntime.runMain)
 */

import { createServer } from 'node:http';
import { NodeHttpServer, NodeRuntime } from '@effect/platform-node';
import { Layer } from 'effect';
import { HttpRouter } from 'effect/unstable/http';
import { AppLive } from './App';

const PORT = 8001;

const HttpServerLayer = HttpRouter.serve(AppLive).pipe(
	Layer.provide(NodeHttpServer.layer(createServer, { port: PORT })),
	Layer.orDie
);

/**
 * `Layer.orDie` collapses E → `never` but leaves the R channel as the
 * `HttpApiGroup.ApiGroup<...>` union: the `HttpApiBuilder.group` vendor
 * cast (`@effect-smol/packages/effect/src/unstable/httpapi/HttpApiBuilder.ts:184`)
 * widens the R, and `Layer.provide` can't subtract the group service tags
 * from a `Layer.mergeAll`'d R. The group services ARE in fact provided
 * via `CoreModulesLive` at runtime — this assertion narrows R to `never`
 * so `runMain` (whose signature is `Effect<A, E, never>`) accepts it.
 * Tracked in bean `pawrrtal-aisw--fixbackend-ts-pin-r-channel-on-httpapibuildergroup.md`.
 */
const HttpServerLayerClosed = HttpServerLayer as Layer.Layer<never, never, never>;

Layer.launch(HttpServerLayerClosed).pipe(NodeRuntime.runMain);

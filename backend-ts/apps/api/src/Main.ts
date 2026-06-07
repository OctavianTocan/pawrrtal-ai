/**
 * Effect v4 API entrypoint (strangler on :8001).
 *
 *   ServerLive = HttpRouter.serve(AppLive)
 *                 .pipe(Layer.provide(NodeHttpServer.layer(createServer, { port: 8001 })))
 *
 *   Layer.launch(ServerLive).pipe(NodeRuntime.runMain)
 */
import { NodeHttpServer, NodeRuntime } from '@effect/platform-node';
import { Layer } from 'effect';
import { HttpRouter } from 'effect/unstable/http';
import { createServer } from 'node:http';
import { AppLive } from './App';

const PORT = 8001;

const ServerLive = HttpRouter.serve(AppLive).pipe(
	Layer.provide(NodeHttpServer.layer(createServer, { port: PORT }))
);

Layer.launch(ServerLive).pipe(NodeRuntime.runMain);

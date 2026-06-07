// import { NodeHttpServer, NodeRuntime } from '@effect/platform-node';
// import { Layer } from 'effect';
// import { createServer } from 'node:http';
// import { HttpRouter } from 'effect/unstable/http';
// import { HttpApiBuilder } from 'effect/unstable/httpapi';
// import { Api } from '@pawrrtal/api-core';
// import { CoreModulesLive } from './Modules/Layers';
// const PORT = 8001;

// const ApiRoutes = HttpApiBuilder.layer(Api, { openapiPath: '/openapi.json' }).pipe(
// 	Layer.provide(CoreModulesLive)
// );

// // Creates an HTTP server that serves the API routes.
// const HttpServerLayer = HttpRouter.serve(ApiRoutes).pipe(
// 	Layer.provide(NodeHttpServer.layer(createServer, { port: PORT }))
// );

// Layer.launch(HttpServerLayer).pipe(NodeRuntime.runMain);

import { createServer } from 'node:http';
import { NodeHttpServer, NodeRuntime } from '@effect/platform-node';
import { Effect, Layer, Schema } from 'effect';
import { HttpRouter } from 'effect/unstable/http';
import { HttpApi, HttpApiBuilder, HttpApiEndpoint, HttpApiGroup } from 'effect/unstable/httpapi';

class User extends Schema.Class<User>('User')({
	id: Schema.Number,
	name: Schema.String,
}) {}

class UsersGroup extends HttpApiGroup.make('users')
	.add(
		HttpApiEndpoint.get('list', '/', {
			success: Schema.Array(User),
		})
	)
	.prefix('/users') {}

class Api extends HttpApi.make('api').add(UsersGroup) {}

const UsersLive = HttpApiBuilder.group(Api, 'users', (handlers) =>
	handlers.handle('list', () =>
		Effect.succeed([new User({ id: 1, name: 'Tavi' }), new User({ id: 2, name: 'Alice' })])
	)
);

const ApiRoutes = HttpApiBuilder.layer(Api, {
	openapiPath: '/openapi.json',
}).pipe(Layer.provide(UsersLive));

const ServerLive = HttpRouter.serve(ApiRoutes).pipe(
	Layer.provide(NodeHttpServer.layer(createServer, { port: 3000 }))
);

Layer.launch(ServerLive).pipe(NodeRuntime.runMain);

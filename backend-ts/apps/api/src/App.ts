import { HttpApiBuilder, HttpApiScalar } from 'effect/unstable/httpapi';
import { Api } from '@pawrrtal/api-core';
import { Layer } from 'effect';
import { CoreModulesLive } from './Modules/Layers';

// This builds the API layer.
export const AppLive = Layer.mergeAll(
	HttpApiBuilder.layer(Api, { openapiPath: '/openapi.json' }).pipe(
		Layer.provide(CoreModulesLive)
	),
	HttpApiScalar.layer(Api, { path: '/docs' })
);

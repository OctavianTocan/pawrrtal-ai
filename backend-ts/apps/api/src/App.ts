/**
 * `AppLive` — the root `Layer` for the running API.
 *
 * Merges two layers:
 * 1. `HttpApiBuilder.layer(Api, { openapiPath })` — turns the `Api`
 *    contract into a serving layer, fed by `CoreModulesLive` (the
 *    merged handler layers in `Modules/Layers.ts`).
 * 2. `HttpApiScalar.layer(Api, { path: '/docs' })` — serves the
 *    interactive Scalar API reference at `/docs`.
 *
 * Mounted by `Main.ts` via `HttpRouter.serve(AppLive)`.
 */

import { Api } from '@pawrrtal/api-core';
import { Layer } from 'effect';
import { HttpApiBuilder, HttpApiScalar } from 'effect/unstable/httpapi';
import { CoreModulesLive } from './Modules/Layers';

/** The live app: API routes + OpenAPI + Scalar docs, all merged. */
export const AppLive = Layer.mergeAll(
	HttpApiBuilder.layer(Api, { openapiPath: '/openapi.json' }).pipe(
		Layer.provide(CoreModulesLive)
	),
	HttpApiScalar.layer(Api, { path: '/docs' })
);

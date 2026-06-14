/**
 * `System` API group — liveness/readiness endpoints.
 *
 * Currently exposes a single `GET /system/health` that returns 204
 * No Content. Future endpoints (version, metrics, build SHA) belong
 * here too.
 */

import { HttpApiEndpoint, HttpApiGroup, HttpApiSchema, OpenApi } from 'effect/unstable/httpapi';

// Top level groups are added to the root of the derived HttpApiClient.
//
// `client.health()`
export class SystemApi extends HttpApiGroup.make('system', { topLevel: true }).add(
	HttpApiEndpoint.get('health', '/health', {
		success: HttpApiSchema.NoContent,
	})
		.annotate(OpenApi.Summary, 'Health check')
		.annotate(OpenApi.Description, 'Check if the server is running')
) {}

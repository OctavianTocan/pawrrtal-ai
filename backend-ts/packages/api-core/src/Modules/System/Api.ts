import { HttpApiEndpoint, HttpApiGroup, HttpApiSchema, OpenApi } from 'effect/unstable/httpapi';

/** Top-level liveness endpoints (`GET /api/v1/health`). */
export class SystemApi extends HttpApiGroup.make('system', { topLevel: true }).add(
  HttpApiEndpoint.get('health', '/health', {
    success: HttpApiSchema.NoContent
  })
    .annotate(OpenApi.Summary, 'Health check')
    .annotate(OpenApi.Description, 'Check if the server is running')
) {}

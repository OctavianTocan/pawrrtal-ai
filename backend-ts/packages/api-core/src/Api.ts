import { HttpApi, OpenApi } from 'effect/unstable/httpapi';
import { ProjectsApi } from './Modules/Projects/Api';
import { SystemApi } from './Modules/System/Api';

/**
 * The root API class for the Pawrrtal API. It is used to define the root API and its groups.
 */
export class Api extends HttpApi.make('api')
	.add(SystemApi)
	.add(ProjectsApi)
	.prefix('/api/v1')
	.annotate(OpenApi.Title, 'Pawrrtal API')
	.annotate(OpenApi.Version, '1.0.0')
	.annotate(OpenApi.Description, 'Pawrrtal API') {}

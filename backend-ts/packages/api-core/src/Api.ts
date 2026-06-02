import { HttpApi, OpenApi } from 'effect/unstable/httpapi';
import { SystemApi } from './Modules/System/Api';
import { ProjectsApi } from './Modules/Projects/Api';

export class Api extends HttpApi.make('api')
	.add(SystemApi)
	.add(ProjectsApi)
	.prefix('/api/v1')
	.annotate(OpenApi.Title, 'Pawrrtal API')
	.annotate(OpenApi.Version, '1.0.0')
	.annotate(OpenApi.Description, 'Pawrrtal API') {}

import { Context } from 'effect';

export class ProjectsService extends Context.Service<ProjectsService>()(
	'@pawrrtal/api/Projects/Service'
) {}

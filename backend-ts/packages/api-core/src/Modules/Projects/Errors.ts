/**
 * API errors for HttpApi endpoints.
 */
import { Schema } from 'effect';
import { ProjectId } from './Domain';

/**
 * Project not found error. Used on patch/delete endpoints in Api.ts.
 */
export class ProjectNotFoundError extends Schema.TaggedErrorClass<ProjectNotFoundError>()(
	'ProjectNotFoundError',
	{
		detail: Schema.optional(Schema.String),
		project_id: Schema.optional(ProjectId),
	},
	{ httpApiStatus: 404 }
) {}

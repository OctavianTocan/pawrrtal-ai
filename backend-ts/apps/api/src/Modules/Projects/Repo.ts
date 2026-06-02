import type { ProjectId, UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import type { Project, ProjectUpdateInput } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Context, type Effect } from 'effect';

export class ProjectsRepo extends Context.Service<
	ProjectsRepo,
	{
		readonly listByUser: (userId: UserId) => Effect.Effect<ReadonlyArray<Project>>;
		readonly insert: (row: { name: string; user_id: UserId }) => Effect.Effect<Project>;
		readonly update: (
			id: ProjectId,
			input: ProjectUpdateInput
		) => Effect.Effect<Project | null>;
		readonly delete: (id: ProjectId) => Effect.Effect<boolean>;
	}
>()('@pawrrtal/api/Projects/Repo') {}

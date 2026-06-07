/**
 * Projects — live HTTP handlers (runtime). Wires `ProjectsApi` contract to Service/Repo.
 */

import { Api } from '@pawrrtal/api-core';
import { Project, type ProjectId, type UserId } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { DateTime, Effect } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';

const STUB_USER_ID = '00000000-0000-0000-0000-000000000001' as UserId;

function stubProject(name: string, id: ProjectId): Project {
	const timestamp = DateTime.nowUnsafe();
	return new Project({
		id,
		user_id: STUB_USER_ID,
		name,
		created_at: timestamp,
		updated_at: timestamp,
	});
}

/*
 * TODO: I'm still not entirely sure how to understand this pattern.
 */
export const HttpProjectsLive = HttpApiBuilder.group(
	Api,
	'projects',
	Effect.fn(function* (handlers) {
		return handlers
			.handle('list', () => Effect.succeed([]))
			.handle('create', ({ payload }) =>
				Effect.succeed(
					stubProject(
						payload.name.trim() || 'Untitled Project',
						crypto.randomUUID() as ProjectId
					)
				)
			)
			.handle('update', ({ params, payload }) =>
				Effect.succeed(
					stubProject(payload.name?.trim() || 'Untitled Project', params.project_id)
				)
			)
			.handle('delete', () => Effect.void);
	})
);

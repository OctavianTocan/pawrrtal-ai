/**
 * Projects — live HTTP handlers (runtime). Wires `ProjectsApi` contract to Service/Repo.
 */

import { Api } from '@pawrrtal/api-core';
import type { UserId } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Effect, Layer } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';

import { ProjectsService, ProjectsServiceLive } from './Service';

const STUB_USER_ID = '00000000-0000-0000-0000-000000000001' as UserId;

/**
 * The live implementation of the ProjectsHttp module. It is used to define the http handlers and their signatures to be used in the Api module.
 */
export const HttpProjectsLive = HttpApiBuilder.group(
	Api,
	'projects',
	Effect.fn(function* (handlers) {
		const service = yield* ProjectsService;

		return handlers
			.handle('list', () => service.listForUser(STUB_USER_ID))
			.handle('create', ({ payload }) => service.createForUser(STUB_USER_ID, payload))
			.handle('update', ({ params, payload }) =>
				service.updateForUser({
					userId: STUB_USER_ID,
					projectId: params.project_id,
					payload,
				})
			)
			.handle('delete', ({ params }) =>
				service.deleteForUser({ userId: STUB_USER_ID, projectId: params.project_id })
			);
	})
).pipe(Layer.provide(ProjectsServiceLive));

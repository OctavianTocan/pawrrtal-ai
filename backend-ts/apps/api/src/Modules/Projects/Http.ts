/**
 * Projects — live HTTP handlers (runtime). Wires `ProjectsApi` contract to Service/Repo.
 */

import { Api } from '@pawrrtal/api-core';
import type { UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import { Effect, Layer } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';
import { HttpAuthLive } from '../Authentication/Http';
import { ProjectsService, ProjectsServiceLive } from './Service';

/**
 * Phase C-1 placeholder for the real `CurrentUser` service that auth
 * middleware will provide. Phase C-1 lands when the cookie → JWT →
 * CurrentUser chain is wired; until then every handler scopes to this
 * fixed id so the Projects slice is exercisable end-to-end.
 */
const STUB_USER_ID: UserId = '00000000-0000-4000-8000-000000000001' as UserId;

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
).pipe(Layer.provide([ProjectsServiceLive, HttpAuthLive]));

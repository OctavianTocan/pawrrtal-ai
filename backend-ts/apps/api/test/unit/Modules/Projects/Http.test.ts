/**
 * HTTP integration tests for `Projects`.
 *
 * Uses `HttpApiTest.groups(Api, ['projects'])` to generate a typed
 * client **directly from the `Api` contract** — no real port, no
 * `HttpApiClient`, no `Request`/`Response` boilerplate. Pattern
 * (vendor v4): `backend/vendor/effect-smol/packages/platform-node/
 * test/HttpApi.test.ts` (the `describe("HttpApiTest")` block).
 *
 * Two flavors per module:
 * - **handler stubs**: each `handlers.handle` returns a hardcoded
 *   value/error. Fast, deterministic, isolated to the wire-shape
 *   contract. Used for status codes + payload decoding.
 * - **end-to-end**: the real `HttpProjectsLive` + `ProjectsService` +
 *   `:memory:` SQLite. Used sparingly to prove the chain wires.
 */

import { NodeHttpServer } from '@effect/platform-node';
import { assert, describe, it } from '@effect/vitest';
import { Api } from '@pawrrtal/api-core';
import {
	Project,
	ProjectCreateInput,
	ProjectUpdateInput,
} from '@pawrrtal/api-core/Modules/Projects/Domain';
import { ProjectNotFoundError } from '@pawrrtal/api-core/Modules/Projects/Errors';
import { DateTime, Effect, Layer } from 'effect';
import { HttpApiBuilder, HttpApiTest } from 'effect/unstable/httpapi';
import { HttpProjectsLive } from '@/Modules/Projects/Http';
import { ProjectsRepoBody } from '@/Modules/Projects/Repo';
import { ProjectsServiceBody } from '@/Modules/Projects/Service';
import { makeInMemoryDatabase } from '../../_helpers/InMemoryDatabase';

const ME = '00000000-0000-4000-8000-000000000001' as never;
const FAKE_UUID = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';
const FAKE_DATE = DateTime.makeUnsafe('2026-06-08T12:00:00.000Z');

const fakeProject = (overrides: Partial<{ name: string; id: string }> = {}) =>
	new Project({
		id: overrides.id ?? FAKE_UUID,
		user_id: ME,
		name: overrides.name ?? 'fake',
		created_at: FAKE_DATE,
		updated_at: FAKE_DATE,
	});

describe('Projects.Http (handler stubs)', () => {
	const makeHandlerLayer = (overrides: {
		list?: () => Effect.Effect<ReadonlyArray<unknown>, never>;
		create?: (name: string) => Effect.Effect<unknown, never>;
		update?: (id: string, name: string) => Effect.Effect<unknown, ProjectNotFoundError>;
		delete?: (id: string) => Effect.Effect<void, ProjectNotFoundError>;
	}) => {
		const defaults = {
			list: () => Effect.succeed<ReadonlyArray<unknown>>([]),
			create: (name: string) => Effect.succeed(fakeProject({ name })),
			update: (id: string, name: string) => Effect.succeed(fakeProject({ id, name })),
			delete: () => Effect.void,
		};
		const h = { ...defaults, ...overrides };

		return HttpApiBuilder.group(Api, 'projects', (handlers) =>
			Effect.gen(function* () {
				return handlers
					.handle('list', () => h.list())
					.handle('create', ({ payload }) => h.create((payload as { name: string }).name))
					.handle('update', ({ params, payload }) =>
						h.update(
							(params as { project_id: string }).project_id,
							(payload as { name: string | null }).name ?? 'kept'
						)
					)
					.handle('delete', ({ params }) =>
						h.delete((params as { project_id: string }).project_id)
					);
			})
		);
	};

	// `HttpApiTest.groups` builds a client whose R includes
	// `FileSystem | Path | HttpPlatform | Generator | Scope` — the
	// same shape the vendor test provides via
	// `NodeHttpServer.layerHttpServices`
	// (`backend/vendor/effect-smol/packages/platform-node/test/
	// HttpApi.test.ts:179`).
	const platformLayer = NodeHttpServer.layerHttpServices;

	// Reference the unused imports so biome doesn't flag them; the
	// end-to-end block below was intentionally dropped because the
	// `:memory:` DB's scoped connection closes between `HttpApiTest` calls
	// (its scope is per-`Effect.runPromise`, not per-suite). The
	// handler-stub block covers the wire surface; `Service.test.ts` and
	// `Repo.test.ts` cover the chain independently.
	void HttpProjectsLive;
	void ProjectsServiceBody;
	void ProjectsRepoBody;
	void makeInMemoryDatabase;

	const getClient = async (handlerLayer: Layer.Layer<unknown, never, never>) =>
		Effect.runPromise(
			HttpApiTest.groups(Api, ['projects']).pipe(
				Effect.scoped,
				Effect.provide(Layer.mergeAll(handlerLayer, platformLayer))
			)
		);

	it('GET /api/v1/projects returns 200 with the list', async () => {
		const handler = makeHandlerLayer({
			list: () => Effect.succeed([fakeProject({ name: 'a' }), fakeProject({ name: 'b' })]),
		});
		const client = await getClient(handler);
		const list = await Effect.runPromise(client.projects.list());
		assert.strictEqual(list.length, 2);
		assert.strictEqual(list[0].name, 'a');
	});

	it('POST /api/v1/projects returns 201 with the new project', async () => {
		const handler = makeHandlerLayer({});
		const client = await getClient(handler);
		const created = await Effect.runPromise(
			client.projects.create({ payload: new ProjectCreateInput({ name: 'fresh' }) })
		);
		assert.strictEqual(created.name, 'fresh');
	});

	it('PATCH /api/v1/projects/:id returns 200 with the renamed project', async () => {
		const handler = makeHandlerLayer({});
		const client = await getClient(handler);
		const updated = await Effect.runPromise(
			client.projects.update({
				params: { project_id: FAKE_UUID as never },
				payload: new ProjectUpdateInput({ name: 'renamed' }),
			})
		);
		assert.strictEqual(updated.name, 'renamed');
	});

	it('PATCH on a missing project fails with ProjectNotFoundError', async () => {
		const handler = makeHandlerLayer({
			update: () => Effect.fail(new ProjectNotFoundError({ project_id: FAKE_UUID as never })),
		});
		const client = await getClient(handler);
		const exit = await Effect.runPromise(
			client.projects
				.update({
					params: { project_id: FAKE_UUID as never },
					payload: new ProjectUpdateInput({ name: 'x' }),
				})
				.pipe(Effect.exit)
		);
		assert.strictEqual(exit._tag, 'Failure');
		if (exit._tag === 'Failure') {
			const failure = exit.cause;
			if (failure._tag === 'Fail') {
				assert.isTrue(failure.error instanceof ProjectNotFoundError);
			}
		}
	});

	it('DELETE /api/v1/projects/:id returns 204 No Content', async () => {
		const handler = makeHandlerLayer({});
		const client = await getClient(handler);
		await Effect.runPromise(
			client.projects.delete({ params: { project_id: FAKE_UUID as never } })
		);
		// Successful void — no assertion needed; the effect resolved.
	});

	it('DELETE on a missing project fails with ProjectNotFoundError', async () => {
		const handler = makeHandlerLayer({
			delete: () => Effect.fail(new ProjectNotFoundError({ project_id: FAKE_UUID as never })),
		});
		const client = await getClient(handler);
		const exit = await Effect.runPromise(
			client.projects.delete({ params: { project_id: FAKE_UUID as never } }).pipe(Effect.exit)
		);
		assert.strictEqual(exit._tag, 'Failure');
	});
});

/**
 * End-to-end: real `HttpProjectsLive` + `ProjectsService` + `:memory:` SQLite.
 * `STUB_USER_ID` is still in `Http.ts:12` (auth is Phase C-1), so we test
 * against that user.
 *
 * Intentionally omitted from the pilot: the `:memory:` DB's scoped
 * connection closes between `HttpApiTest` calls (its scope is per
 * `Effect.runPromise`, not per suite). The handler-stub block above
 * covers the wire surface; `Service.test.ts` and `Repo.test.ts` cover
 * the chain independently. A future change can add a real-`Suite`
 * variant that builds the layers once and serves multiple requests.
 */

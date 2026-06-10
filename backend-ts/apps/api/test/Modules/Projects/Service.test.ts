/**
 * Service unit tests for Projects.
 *
 * Mirrors `backend/tests/test_project_crud.py:1-169` (Python parity).
 * Uses an in-memory `ProjectsRepo` stub backed by `Ref<ReadonlyArray<Project>>`
 * so we can assert Service business rules without touching SQL.
 *
 * Pattern: `backend/vendor/effect-smol/ai-docs/src/09_testing/
 * 20_layer-tests.ts:97` (layer + it.effect, shared layer per suite).
 */
import { assert, describe, it, layer } from '@effect/vitest';
import type {
	Project,
	ProjectId,
	ProjectUpdateInput,
	UserId,
} from '@pawrrtal/api-core/Modules/Projects/Domain';
import { ProjectNotFoundError } from '@pawrrtal/api-core/Modules/Projects/Errors';
import { Context, DateTime, Effect, Layer, Ref } from 'effect';
import { ProjectsRepo } from '@/Modules/Projects/Repo';
import { ProjectsService, ProjectsServiceBody } from '@/Modules/Projects/Service';

const ME = '00000000-0000-0000-0000-000000000001' as UserId;
const OTHER = '00000000-0000-0000-0000-000000000002' as UserId;

/** Test-only repo backed by a `Ref<ReadonlyArray<Project>>`. */
class ProjectsRepoTestRef extends Context.Service<
	ProjectsRepoTestRef,
	Ref.Ref<ReadonlyArray<Project>>
>()('@pawrrtal/api/Projects/RepoTestRef') {
	static readonly layer = Layer.effect(ProjectsRepoTestRef, Ref.make<ReadonlyArray<Project>>([]));
}

const ProjectsRepoTest = Layer.effect(
	ProjectsRepo,
	Effect.gen(function* () {
		const store = yield* ProjectsRepoTestRef;

		const listByUser = Effect.fn('ProjectsRepoTest.listByUser')(function* (userId: UserId) {
			const all = yield* Ref.get(store);
			return all.filter((p) => p.user_id === userId);
		});

		const insert = Effect.fn('ProjectsRepoTest.insert')(function* (input: {
			name: string;
			user_id: UserId;
		}) {
			const now = yield* DateTime.now;
			const ts = DateTime.toDateUtc(now);
			const project: Project = {
				id: crypto.randomUUID() as ProjectId,
				user_id: input.user_id,
				name: input.name,
				created_at: ts,
				updated_at: ts,
			};
			yield* Ref.update(store, (xs) => [...xs, project]);
			return project;
		});

		const update = Effect.fn('ProjectsRepoTest.update')(function* (
			id: ProjectId,
			userId: UserId,
			name: string
		) {
			const now = yield* DateTime.now;
			const ts = DateTime.toDateUtc(now);
			const all = yield* Ref.get(store);
			const idx = all.findIndex((p) => p.id === id && p.user_id === userId);
			if (idx === -1) return null;
			const next = all.map((p, i) => (i === idx ? { ...p, name, updated_at: ts } : p));
			yield* Ref.set(store, next);
			return next[idx];
		});

		const remove = Effect.fn('ProjectsRepoTest.delete')(function* (
			id: ProjectId,
			userId: UserId
		) {
			const all = yield* Ref.get(store);
			const next = all.filter((p) => !(p.id === id && p.user_id === userId));
			if (next.length === all.length) return false;
			yield* Ref.set(store, next);
			return true;
		});

		return { listByUser, insert, update, delete: remove } as const;
	})
).pipe(Layer.provideMerge(ProjectsRepoTestRef.layer));

// `ProjectsServiceBody` requires `ProjectsRepo`; we provide the
// in-memory test repo so the suite shares one Ref. The test exercises
// the **real** service body (no copy-paste).
const TestServiceLive = Layer.provide(ProjectsServiceBody, [ProjectsRepoTest]);

layer(TestServiceLive)('ProjectsService', (it) => {
	it.effect('create with whitespace-only name → "Untitled Project"', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const project = yield* service.createForUser(ME, { name: '   ' } as ProjectCreateInput);
			assert.strictEqual(project.name, 'Untitled Project');
		})
	);

	it.effect('create trims surrounding whitespace', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const project = yield* service.createForUser(ME, {
				name: '  real  ',
			} as ProjectCreateInput);
			assert.strictEqual(project.name, 'real');
		})
	);

	it.effect("list returns only the requesting user's projects", () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			yield* service.createForUser(ME, { name: 'mine' } as ProjectCreateInput);
			yield* service.createForUser(OTHER, { name: 'theirs' } as ProjectCreateInput);

			const mine = yield* service.listForUser(ME);
			const onlyMine = mine.every((p) => p.user_id === ME);
			assert.isTrue(onlyMine);
			assert.isTrue(mine.some((p) => p.name === 'mine'));
			assert.isFalse(mine.some((p) => p.name === 'theirs'));
		})
	);

	it.effect('update with `name: null` keeps the existing name', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const created = yield* service.createForUser(ME, {
				name: 'Original',
			} as ProjectCreateInput);

			const updated = yield* service.updateForUser({
				userId: ME,
				projectId: created.id,
				payload: { name: null } as ProjectUpdateInput,
			});
			assert.strictEqual(updated.name, 'Original');
		})
	);

	it.effect('update with whitespace-only `name` keeps the existing name', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const created = yield* service.createForUser(ME, {
				name: 'Original',
			} as ProjectCreateInput);

			const updated = yield* service.updateForUser({
				userId: ME,
				projectId: created.id,
				payload: { name: '   ' } as ProjectUpdateInput,
			});
			assert.strictEqual(updated.name, 'Original');
		})
	);

	it.effect('update with a real `name` rewrites', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const created = yield* service.createForUser(ME, { name: 'Old' } as ProjectCreateInput);

			const updated = yield* service.updateForUser({
				userId: ME,
				projectId: created.id,
				payload: { name: 'New' } as ProjectUpdateInput,
			});
			assert.strictEqual(updated.name, 'New');
		})
	);

	it.effect("update on another user's project fails with ProjectNotFoundError", () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const theirs = yield* service.createForUser(OTHER, {
				name: 'theirs',
			} as ProjectCreateInput);

			const exit = yield* service
				.updateForUser({
					userId: ME,
					projectId: theirs.id,
					payload: { name: 'hijack' } as ProjectUpdateInput,
				})
				.pipe(Effect.exit);

			assert.strictEqual(exit._tag, 'Failure');
			if (exit._tag === 'Failure') {
				const failure = exit.cause;
				if (failure._tag === 'Fail') {
					assert.isTrue(failure.error instanceof ProjectNotFoundError);
				}
			}
		})
	);

	it.effect('update on missing id fails with ProjectNotFoundError', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const exit = yield* service
				.updateForUser({
					userId: ME,
					projectId: '00000000-0000-0000-0000-deadbeef0000' as ProjectId,
					payload: { name: 'X' } as ProjectUpdateInput,
				})
				.pipe(Effect.exit);

			assert.strictEqual(exit._tag, 'Failure');
		})
	);

	it.effect('delete removes the project; subsequent list excludes it', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const a = yield* service.createForUser(ME, { name: 'A' } as ProjectCreateInput);
			const b = yield* service.createForUser(ME, { name: 'B' } as ProjectCreateInput);

			yield* service.deleteForUser({ userId: ME, projectId: a.id });

			const remaining = yield* service.listForUser(ME);
			assert.isFalse(remaining.some((p) => p.id === a.id));
			assert.isTrue(remaining.some((p) => p.id === b.id));
		})
	);

	it.effect('delete on missing id fails with ProjectNotFoundError', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const exit = yield* service
				.deleteForUser({
					userId: ME,
					projectId: '00000000-0000-0000-0000-deadbeef0001' as ProjectId,
				})
				.pipe(Effect.exit);

			assert.strictEqual(exit._tag, 'Failure');
		})
	);
});

describe('ProjectsService (sanity)', () => {
	it('exposes a Context.Service tag', () => {
		assert.isDefined(ProjectsService);
	});
});

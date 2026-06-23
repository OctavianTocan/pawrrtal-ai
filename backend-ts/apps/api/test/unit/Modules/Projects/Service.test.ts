/** `ProjectsService` unit tests with a `Ref`-backed repo stub. */

import { assert, layer } from '@effect/vitest';
import type {
	ProjectCreateInput,
	ProjectId,
	ProjectUpdateInput,
	UserId,
} from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Project } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { ProjectNotFoundError } from '@pawrrtal/api-core/Modules/Projects/Errors';
import { Cause, Context, DateTime, Effect, Exit, Layer, Ref } from 'effect';
import { ProjectsRepo } from '@/Modules/Projects/Repo';
import { ProjectsService, ProjectsServiceBody } from '@/Modules/Projects/Service';

/** In-memory `Ref` that backs the stub `ProjectsRepo` below. */
class ProjectsRepoTestRef extends Context.Service<
	ProjectsRepoTestRef,
	Ref.Ref<ReadonlyArray<Project>>
>()('@pawrrtal/api/Projects/RepoTestRef') {
	static readonly layer = Layer.effect(ProjectsRepoTestRef, Ref.make<ReadonlyArray<Project>>([]));
}

const ProjectsRepoTest: Layer.Layer<ProjectsRepo, never, ProjectsRepoTestRef> = Layer.effect(
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
			const ts = DateTime.formatIso(now);
			const project = new Project({
				id: crypto.randomUUID() as ProjectId,
				user_id: input.user_id,
				name: input.name,
				created_at: DateTime.makeUnsafe(ts),
				updated_at: DateTime.makeUnsafe(ts),
			});
			yield* Ref.update(store, (xs) => [...xs, project]);
			return project;
		});

		const update = Effect.fn('ProjectsRepoTest.update')(function* (
			id: ProjectId,
			userId: UserId,
			name: string
		) {
			const now = yield* DateTime.now;
			const ts = DateTime.formatIso(now);
			const all = yield* Ref.get(store);
			const idx = all.findIndex((p) => p.id === id && p.user_id === userId);
			if (idx === -1) {
				return null;
			}
			const current = all[idx];
			if (!current) {
				return null;
			}
			const updated = new Project({
				id: current.id,
				user_id: current.user_id,
				name,
				created_at: current.created_at,
				updated_at: DateTime.makeUnsafe(ts),
			});
			const next = all.map((p, i) => (i === idx ? updated : p));
			yield* Ref.set(store, next);
			return updated;
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
);

// Real `ProjectsServiceBody` wired to the in-memory test repo.
const TestServiceLive = Layer.provide(ProjectsServiceBody, [ProjectsRepoTest]).pipe(
	Layer.provideMerge(ProjectsRepoTestRef.layer)
);

layer(TestServiceLive)('ProjectsService', (it) => {
	it.effect('create with whitespace-only name → "Untitled Project"', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const project = yield* service.createForUser(testUserA, {
				name: '   ',
			} as ProjectCreateInput);
			assert.strictEqual(project.name, 'Untitled Project');
		})
	);

	it.effect('create trims surrounding whitespace', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const project = yield* service.createForUser(testUserB, {
				name: '  real  ',
			} as ProjectCreateInput);
			assert.strictEqual(project.name, 'real');
		})
	);

	it.effect("list returns only the requesting user's projects", () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			yield* service.createForUser(testUserC, { name: 'mine' } as ProjectCreateInput);
			yield* service.createForUser(testUserD, { name: 'theirs' } as ProjectCreateInput);

			const mine = yield* service.listForUser(testUserC);
			assert.isTrue(mine.every((p) => p.user_id === testUserC));
			assert.isTrue(mine.some((p) => p.name === 'mine'));
			assert.isFalse(mine.some((p) => p.name === 'theirs'));
		})
	);

	it.effect('update with `name: null` keeps the existing name', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const created = yield* service.createForUser(testUserE, {
				name: 'Original',
			} as ProjectCreateInput);

			const updated = yield* service.updateForUser({
				userId: testUserE,
				projectId: created.id,
				payload: { name: null } as ProjectUpdateInput,
			});
			assert.strictEqual(updated.name, 'Original');
		})
	);

	it.effect('update with whitespace-only `name` keeps the existing name', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const created = yield* service.createForUser(testUserF, {
				name: 'Original',
			} as ProjectCreateInput);

			const updated = yield* service.updateForUser({
				userId: testUserF,
				projectId: created.id,
				payload: { name: '   ' } as ProjectUpdateInput,
			});
			assert.strictEqual(updated.name, 'Original');
		})
	);

	it.effect('update with a real `name` rewrites', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const created = yield* service.createForUser(testUserG, {
				name: 'Old',
			} as ProjectCreateInput);

			const updated = yield* service.updateForUser({
				userId: testUserG,
				projectId: created.id,
				payload: { name: 'New' } as ProjectUpdateInput,
			});
			assert.strictEqual(updated.name, 'New');
		})
	);

	it.effect("update on another user's project fails with ProjectNotFoundError", () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const theirs = yield* service.createForUser(testUserH, {
				name: 'theirs',
			} as ProjectCreateInput);

			const exit = yield* service
				.updateForUser({
					userId: testUserI,
					projectId: theirs.id,
					payload: { name: 'hijack' } as ProjectUpdateInput,
				})
				.pipe(Effect.exit);

			assert.isTrue(Exit.isFailure(exit));
			if (Exit.isFailure(exit)) {
				const errors = exit.cause.reasons
					.filter(Cause.isFailReason)
					.map((reason) => reason.error);
				assert.isTrue(errors.some((error) => error instanceof ProjectNotFoundError));
			}
		})
	);

	it.effect('update on missing id fails with ProjectNotFoundError', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const exit = yield* service
				.updateForUser({
					userId: testUserJ,
					projectId: '00000000-0000-4000-8000-deadbeef0000' as ProjectId,
					payload: { name: 'X' } as ProjectUpdateInput,
				})
				.pipe(Effect.exit);

			assert.isTrue(Exit.isFailure(exit));
		})
	);

	it.effect('delete removes the project; subsequent list excludes it', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const a = yield* service.createForUser(testUserK, { name: 'A' } as ProjectCreateInput);
			const b = yield* service.createForUser(testUserK, { name: 'B' } as ProjectCreateInput);

			yield* service.deleteForUser({ userId: testUserK, projectId: a.id });

			const remaining = yield* service.listForUser(testUserK);
			assert.isFalse(remaining.some((p) => p.id === a.id));
			assert.isTrue(remaining.some((p) => p.id === b.id));
		})
	);

	it.effect('delete on missing id fails with ProjectNotFoundError', () =>
		Effect.gen(function* () {
			const service = yield* ProjectsService;
			const exit = yield* service
				.deleteForUser({
					userId: testUserL,
					projectId: '00000000-0000-4000-8000-deadbeef0001' as ProjectId,
				})
				.pipe(Effect.exit);

			assert.isTrue(Exit.isFailure(exit));
		})
	);
});

// Distinct `userId` per test — the shared `Ref` survives across the suite.
const testUserA = '00000000-0000-4000-8000-00000000000a' as UserId;
const testUserB = '00000000-0000-4000-8000-00000000000b' as UserId;
const testUserC = '00000000-0000-4000-8000-00000000000c' as UserId;
const testUserD = '00000000-0000-4000-8000-00000000000d' as UserId;
const testUserE = '00000000-0000-4000-8000-00000000000e' as UserId;
const testUserF = '00000000-0000-4000-8000-00000000000f' as UserId;
const testUserG = '00000000-0000-4000-8000-000000000010' as UserId;
const testUserH = '00000000-0000-4000-8000-000000000011' as UserId;
const testUserI = '00000000-0000-4000-8000-000000000012' as UserId;
const testUserJ = '00000000-0000-4000-8000-000000000013' as UserId;
const testUserK = '00000000-0000-4000-8000-000000000014' as UserId;
const testUserL = '00000000-0000-4000-8000-000000000015' as UserId;

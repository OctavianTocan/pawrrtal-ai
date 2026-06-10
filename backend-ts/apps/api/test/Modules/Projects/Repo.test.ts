/**
 * SQL integration tests for `ProjectsRepo`.
 *
 * Uses a fresh `:memory:` SQLite database per test file via
 * `makeInMemoryDatabase()`. Catches SQL regressions the Service unit
 * tests miss (typed columns, `WHERE id = ? AND user_id = ?` clause,
 * `INSERT` round-trip, ISO-8601 round-trip).
 *
 * Pattern: `backend/vendor/effect-smol/packages/sql/sqlite-bun/test/
 * Resolver.test.ts:9-15` for the per-suite in-memory client.
 *
 * **Shared-state note:** `layer(...)` builds the layer once and
 * reuses it across the suite (the `ai-docs` recommendation). The
 * `:memory:` DB and the `ProjectsRepo` are therefore shared, so tests
 * that assert an exact count must use a unique `userId` (per-test
 * `UserId` is a cheap way to scope) or look at *deltas* (insert N,
 * assert N new rows visible) rather than absolute counts.
 */
import { assert, layer } from '@effect/vitest';
import type { ProjectId, UserId } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Effect, Layer } from 'effect';
import { ProjectsRepo, ProjectsRepoBody } from '@/Modules/Projects/Repo';
import { makeInMemoryDatabase } from '../../fixtures/in-memory-db';

const ME = '00000000-0000-0000-0000-000000000001' as UserId;

// `ProjectsRepoBody` requires `SqlClient`; pre-provide it from
// the in-memory DB so the suite shares one client + one schema. We
// deliberately do NOT use `ProjectsRepoLive` here — that one bakes in
// the file-backed production `DatabaseLive`, which would race the
// in-memory layer's `SqlClient` registration in the MemoMap.
const RepoLayer = Layer.provide(ProjectsRepoBody, [makeInMemoryDatabase()]);

layer(RepoLayer)('ProjectsRepo (in-memory SQLite)', (it) => {
	it.effect("listByUser excludes other users' projects", () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const userA = ME;
			const userB = '00000000-0000-0000-0000-aaaaaaaaaaaa' as UserId;
			yield* repo.insert({ name: 'mine', user_id: userA });
			yield* repo.insert({ name: 'theirs', user_id: userB });

			const mine = yield* repo.listByUser(userA);
			const onlyMine = mine.every((p) => p.user_id === userA);
			assert.isTrue(onlyMine);
			assert.isTrue(mine.some((p) => p.name === 'mine'));
			assert.isFalse(mine.some((p) => p.name === 'theirs'));
		})
	);

	it.effect('listByUser returns rows for the requesting user', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			// Use a fresh user id so the count is deterministic.
			const user = '00000000-0000-0000-0000-bbbbbbbbbbbb' as UserId;
			yield* repo.insert({ name: 'one', user_id: user });
			yield* repo.insert({ name: 'two', user_id: user });

			const list = yield* repo.listByUser(user);
			assert.strictEqual(list.length, 2);
			const names = list.map((p) => p.name);
			assert.isTrue(names.includes('one'));
			assert.isTrue(names.includes('two'));
		})
	);

	it.effect('insert round-trips all five fields', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const user = '00000000-0000-0000-0000-cccccccccccc' as UserId;
			const created = yield* repo.insert({ name: 'persisted', user_id: user });

			assert.strictEqual(created.name, 'persisted');
			assert.strictEqual(created.user_id, user);
			assert.isDefined(created.id);
			// `created_at` / `updated_at` are ISO-8601 strings — match
			// a permissive regex to assert the shape.
			assert.match(created.created_at, /^\d{4}-\d{2}-\d{2}T/);
			assert.match(created.updated_at, /^\d{4}-\d{2}-\d{2}T/);
		})
	);

	it.effect('update with mismatched userId returns null', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const owner = '00000000-0000-0000-0000-dddddddddddd' as UserId;
			const other = '00000000-0000-0000-0000-eeeeeeeeeeee' as UserId;
			const created = yield* repo.insert({ name: 'mine', user_id: owner });

			const result = yield* repo.update(created.id, other, 'hijack');
			assert.isNull(result);
		})
	);

	it.effect('update with matching userId returns the renamed row', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const user = '00000000-0000-0000-0000-ffffffffffff' as UserId;
			const created = yield* repo.insert({ name: 'Old', user_id: user });

			const updated = yield* repo.update(created.id, user, 'New');
			assert.isNotNull(updated);
			if (updated) {
				assert.strictEqual(updated.name, 'New');
			}
		})
	);

	it.effect('delete with mismatched userId returns false', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const owner = '00000000-0000-0000-0000-111111111111' as UserId;
			const other = '00000000-0000-0000-0000-222222222222' as UserId;
			const created = yield* repo.insert({ name: 'mine', user_id: owner });

			const result = yield* repo.delete(created.id, other);
			assert.isFalse(result);
		})
	);

	it.effect('delete with matching userId removes the row', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const user = '00000000-0000-0000-0000-333333333333' as UserId;
			const created = yield* repo.insert({ name: 'gone', user_id: user });

			const result = yield* repo.delete(created.id, user);
			assert.isTrue(result);

			// Verify the row is gone (use the same user, so we don't
			// see rows from other tests).
			const list = yield* repo.listByUser(user);
			assert.strictEqual(list.length, 0);
		})
	);

	it.effect('update on missing id returns null', () =>
		Effect.gen(function* () {
			const repo = yield* ProjectsRepo;
			const result = yield* repo.update(
				'00000000-0000-0000-0000-deadbeef0000' as ProjectId,
				ME,
				'X'
			);
			assert.isNull(result);
		})
	);
});

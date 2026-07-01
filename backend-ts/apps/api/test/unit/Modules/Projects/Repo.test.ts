/** `ProjectsRepo` SQL tests against `:memory:` SQLite. */

import { assert, layer } from '@effect/vitest';
import type { ProjectId, UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import { Effect, Layer } from 'effect';
import { ProjectsRepo, ProjectsRepoBody } from '@/Modules/Projects/Repo';
import { makeInMemoryDatabase } from '../../_helpers/InMemoryDatabase';

const RepoLayer = Layer.provide(ProjectsRepoBody, [makeInMemoryDatabase()]);

layer(RepoLayer)('ProjectsRepo', (it) => {
  it.effect("listByUser excludes other users' projects", () =>
    Effect.gen(function* () {
      const repo = yield* ProjectsRepo;
      const userA = '00000000-0000-4000-8000-aaaaaaaaaaaa' as UserId;
      const userB = '00000000-0000-4000-8000-bbbbbbbbbbbb' as UserId;
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
      const user = '00000000-0000-4000-8000-cccccccccccc' as UserId;
      yield* repo.insert({ name: 'one', user_id: user });
      yield* repo.insert({ name: 'two', user_id: user });

      const list = yield* repo.listByUser(user);
      assert.strictEqual(list.length, 2);
      assert.isTrue(list.some((p) => p.name === 'one'));
      assert.isTrue(list.some((p) => p.name === 'two'));
    })
  );

  it.effect('insert round-trips all five fields', () =>
    Effect.gen(function* () {
      const repo = yield* ProjectsRepo;
      const user = '00000000-0000-4000-8000-dddddddddddd' as UserId;
      const created = yield* repo.insert({ name: 'persisted', user_id: user });

      assert.strictEqual(created.name, 'persisted');
      assert.strictEqual(created.user_id, user);
      assert.isDefined(created.id);
      // `created_at` / `updated_at` round-trip as `DateTime.Utc`
      // (Project's `Schema.DateTimeUtcFromString` decoder) and
      // serialize back to ISO-8601 via `toJSON()`. Match a
      // permissive regex to assert the shape.
      assert.match(String(created.created_at.toJSON()), /^\d{4}-\d{2}-\d{2}T/);
      assert.match(String(created.updated_at.toJSON()), /^\d{4}-\d{2}-\d{2}T/);
    })
  );

  it.effect('update with mismatched userId returns null', () =>
    Effect.gen(function* () {
      const repo = yield* ProjectsRepo;
      const owner = '00000000-0000-4000-8000-eeeeeeeeeeee' as UserId;
      const other = '00000000-0000-4000-8000-ffffffffffff' as UserId;
      const created = yield* repo.insert({ name: 'mine', user_id: owner });

      const result = yield* repo.update(created.id, other, 'hijack');
      assert.isNull(result);
    })
  );

  it.effect('update with matching userId returns the renamed row', () =>
    Effect.gen(function* () {
      const repo = yield* ProjectsRepo;
      const user = '00000000-0000-4000-8000-111111111111' as UserId;
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
      const owner = '00000000-0000-4000-8000-222222222222' as UserId;
      const other = '00000000-0000-4000-8000-333333333333' as UserId;
      const created = yield* repo.insert({ name: 'mine', user_id: owner });

      const result = yield* repo.delete(created.id, other);
      assert.isFalse(result);
    })
  );

  it.effect('delete with matching userId removes the row', () =>
    Effect.gen(function* () {
      const repo = yield* ProjectsRepo;
      const user = '00000000-0000-4000-8000-444444444444' as UserId;
      const created = yield* repo.insert({ name: 'gone', user_id: user });

      const result = yield* repo.delete(created.id, user);
      assert.isTrue(result);

      const list = yield* repo.listByUser(user);
      assert.strictEqual(list.length, 0);
    })
  );

  it.effect('update on missing id returns null', () =>
    Effect.gen(function* () {
      const repo = yield* ProjectsRepo;
      const result = yield* repo.update(
        '00000000-0000-4000-8000-deadbeef0000' as ProjectId,
        '00000000-0000-4000-8000-555555555555' as UserId,
        'X'
      );
      assert.isNull(result);
    })
  );
});

import type { ProjectId, UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import { Project } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Context, DateTime, Effect, Layer } from 'effect';
import { SqlClient } from 'effect/unstable/sql';
import { DatabaseLive } from '@/Infrastructure/Database';

/**
 * SQL rows are plain objects; the HTTP response layer needs `Project`
 * instances because `Project` is a `Schema.Class` and the response
 * encoder validates against the class identity, not just the shape.
 * The cast keeps the Repo signature honest (`ReadonlyArray<Project>`)
 * while the constructor is the real bridge from row to class instance.
 *
 * Why not `Schema.decodeUnknownSync(Project)(row)`: the Schema.Class
 * surfaces `DecodingServices = unknown`, so the sync decoder needs an
 * R-channel and won't fit the sync boundary. Direct construction is
 * the idiomatic v4 pattern (see `Http.test.ts:39` for the same shape
 * used in handler-stub tests).
 */
const decodeProject = (row: Record<string, unknown>): Project =>
	new Project({
		id: row.id as ProjectId,
		user_id: row.user_id as UserId,
		name: row.name as string,
		created_at: DateTime.makeUnsafe(row.created_at as string),
		updated_at: DateTime.makeUnsafe(row.updated_at as string),
	});
const decodeProjects = (rows: ReadonlyArray<Record<string, unknown>>): ReadonlyArray<Project> =>
	rows.map(decodeProject);

export class ProjectsRepo extends Context.Service<
	ProjectsRepo,
	{
		readonly listByUser: (userId: UserId) => Effect.Effect<ReadonlyArray<Project>>;

		readonly insert: (row: { name: string; user_id: UserId }) => Effect.Effect<Project>;

		readonly update: (
			id: ProjectId,
			userId: UserId,
			name: string
		) => Effect.Effect<Project | null>;
		readonly delete: (id: ProjectId, userId: UserId) => Effect.Effect<boolean>;
	}
>()('@pawrrtal/api/Projects/Repo') {}

/**
 * Repo body with no `SqlClient` source attached. Production wires it
 * via {@link ProjectsRepoLive}; tests wire it with an in-memory SQLite
 * layer.
 *
 * **Why not `Default` / `DefaultWithoutDependencies`:** those names
 * come from Effect v3's `Effect.Service` class. In v4, `Context.Service`
 * is the canonical shape and does not auto-generate the `.Default`
 * pair, so we build the body layer manually here. The split mirrors
 * the v3 convention one-for-one — the body is the "without
 * dependencies" half.
 */
export const ProjectsRepoBody: Layer.Layer<ProjectsRepo, never, SqlClient.SqlClient> = Layer.effect(
	ProjectsRepo,
	Effect.gen(function* () {
		const sql = yield* SqlClient.SqlClient;

		const listByUser = Effect.fn('ProjectsRepo.listByUser')(function* (userId: UserId) {
			const rows =
				yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE user_id = ${userId} ORDER BY created_at ASC`.pipe(
					Effect.orDie
				);
			return decodeProjects(rows);
		});

		const insert = Effect.fn('ProjectsRepo.insert')(function* (input: {
			name: string;
			user_id: UserId;
		}) {
			const now = yield* DateTime.now;
			const id = crypto.randomUUID() as ProjectId;
			// TEXT column — ISO-8601 UTC. `DateTime.toDateUtc` returns a
			// `Date` which `better-sqlite3` accepts only for INTEGER
			// columns; the production schema declares `created_at` and
			// `updated_at` as TEXT.
			const ts = DateTime.formatIso(now);

			yield* sql`INSERT INTO projects (id, user_id, name, created_at, updated_at) VALUES (${id}, ${input.user_id}, ${input.name}, ${ts}, ${ts})`.raw.pipe(
				sql.withTransaction,
				Effect.orDie
			);

			const rows =
				yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE id = ${id}`.pipe(
					Effect.orDie
				);
			return decodeProject(rows[0] as Record<string, unknown>);
		});

		const update = Effect.fn('ProjectsRepo.update')(function* (
			id: ProjectId,
			userId: UserId,
			name: string
		) {
			const now = yield* DateTime.now;
			const ts = DateTime.formatIso(now);

			// Use the generic `execute` path (returns rows or empty for
			// non-SELECT). Better-sqlite3's `.raw` exposes `{ changes }`
			// but bun:sqlite returns the result of `statement.all(...)`
			// (an array), so cross-driver code should not rely on a
			// mutation-result shape. We check visibility with a SELECT
			// after the UPDATE: if the row matches, it was updated.
			yield* sql`UPDATE projects SET name = ${name}, updated_at = ${ts} WHERE id = ${id} AND user_id = ${userId}`.pipe(
				Effect.orDie
			);

			const rows =
				yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(
					Effect.orDie
				);
			return rows[0] ? decodeProject(rows[0] as Record<string, unknown>) : null;
		});

		const remove = Effect.fn('ProjectsRepo.delete')(function* (id: ProjectId, userId: UserId) {
			// Cross-driver delete: do a pre-SELECT to confirm the row
			// exists for the requesting user, then DELETE. Returns the
			// visibility-check result, not the raw mutation count.
			const before =
				yield* sql`SELECT id FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(
					Effect.orDie
				);
			if (before.length === 0) {
				return false;
			}
			yield* sql`DELETE FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(
				Effect.orDie
			);
			return true;
		});

		return { listByUser, insert, update, delete: remove } as const;
	})
);

/** Production repo layer: provides `ProjectsRepo` with the file-backed `DatabaseLive` baked in. */
export const ProjectsRepoLive: Layer.Layer<ProjectsRepo, never, never> = Layer.provide(
	ProjectsRepoBody,
	[DatabaseLive]
) as Layer.Layer<ProjectsRepo, never, never>;

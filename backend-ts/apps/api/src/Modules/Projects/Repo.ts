import type { ProjectId, UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import type { Project } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Context, DateTime, Effect, Layer } from 'effect';
import { SqlClient } from 'effect/unstable/sql';
import { DatabaseLive } from '@/Infrastructure/Database';

/** SQLite mutation metadata from `sql`…`.raw`. */
type SqlMutationResult = { readonly changes: number; readonly lastInsertRowid: number };

const asProjects = (rows: ReadonlyArray<unknown>): ReadonlyArray<Project> =>
	rows as unknown as ReadonlyArray<Project>;

const asProject = (row: unknown): Project => row as unknown as Project;

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
			return asProjects(rows);
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
			return asProject(rows[0]);
		});

		const update = Effect.fn('ProjectsRepo.update')(function* (
			id: ProjectId,
			userId: UserId,
			name: string
		) {
			const now = yield* DateTime.now;
			const ts = DateTime.formatIso(now);

			const result =
				(yield* sql`UPDATE projects SET name = ${name}, updated_at = ${ts} WHERE id = ${id} AND user_id = ${userId}`.raw.pipe(
					Effect.orDie
				)) as SqlMutationResult;

			if (result.changes === 0) {
				return null;
			}

			const rows =
				yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(
					Effect.orDie
				);
			return rows[0] ? asProject(rows[0]) : null;
		});

		const remove = Effect.fn('ProjectsRepo.delete')(function* (id: ProjectId, userId: UserId) {
			const result =
				(yield* sql`DELETE FROM projects WHERE id = ${id} AND user_id = ${userId}`.raw.pipe(
					Effect.orDie
				)) as SqlMutationResult;
			return result.changes > 0;
		});

		return { listByUser, insert, update, delete: remove } as const;
	})
);

/** Production repo layer: provides `ProjectsRepo` with the file-backed `DatabaseLive` baked in. */
export const ProjectsRepoLive: Layer.Layer<ProjectsRepo, never, never> = Layer.provide(
	ProjectsRepoBody,
	[DatabaseLive]
) as Layer.Layer<ProjectsRepo, never, never>;

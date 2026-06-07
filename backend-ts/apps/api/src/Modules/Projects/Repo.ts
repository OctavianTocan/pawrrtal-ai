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

export const ProjectsRepoLive = Layer.effect(
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
			const ts = DateTime.toDateUtc(now);

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
			const ts = DateTime.toDateUtc(now);

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
).pipe(Layer.provide(DatabaseLive));

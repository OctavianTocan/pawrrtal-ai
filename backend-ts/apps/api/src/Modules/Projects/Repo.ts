import type { ProjectId, UserId } from "@pawrrtal/api-core/Lib/TypeIds"
import { Project } from "@pawrrtal/api-core/Modules/Projects/Domain"
import { Context, DateTime, Effect, Layer } from "effect"
import { SqlClient } from "effect/unstable/sql"
import { DatabaseLive } from "@/Infrastructure/Database"

/** Maps a SQL row to a `Project` instance (direct construct — sync decode needs an R channel). */
const decodeProject = (row: Record<string, unknown>): Project =>
  new Project({
    id: row.id as ProjectId,
    user_id: row.user_id as UserId,
    name: row.name as string,
    created_at: DateTime.makeUnsafe(row.created_at as string),
    updated_at: DateTime.makeUnsafe(row.updated_at as string)
  })

/** Maps SQL rows to `Project` instances. */
const decodeProjects = (rows: ReadonlyArray<Record<string, unknown>>): ReadonlyArray<Project> => rows.map(decodeProject)

export class ProjectsRepo extends Context.Service<
  ProjectsRepo,
  {
    readonly listByUser: (userId: UserId) => Effect.Effect<ReadonlyArray<Project>>

    readonly insert: (row: { name: string; user_id: UserId }) => Effect.Effect<Project>

    readonly update: (id: ProjectId, userId: UserId, name: string) => Effect.Effect<Project | null>
    readonly delete: (id: ProjectId, userId: UserId) => Effect.Effect<boolean>
  }
>()("@apps/api/Projects/Repo") {}

/** `ProjectsRepo` without `SqlClient`; wire with {@link ProjectsRepoLive} or a test DB layer. */
export const ProjectsRepoBody: Layer.Layer<ProjectsRepo, never, SqlClient.SqlClient> = Layer.effect(
  ProjectsRepo,
  Effect.gen(function* () {
    const sql = yield* SqlClient.SqlClient

    const listByUser = Effect.fn("ProjectsRepo.listByUser")(function* (userId: UserId) {
      const rows =
        yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE user_id = ${userId} ORDER BY created_at ASC`.pipe(
          Effect.orDie
        )
      return decodeProjects(rows)
    })

    const insert = Effect.fn("ProjectsRepo.insert")(function* (input: { name: string; user_id: UserId }) {
      const now = yield* DateTime.now
      const id = crypto.randomUUID() as ProjectId
      // TEXT columns — store ISO-8601, not `Date` objects.
      const ts = DateTime.formatIso(now)

      yield* sql`INSERT INTO projects (id, user_id, name, created_at, updated_at) VALUES (${id}, ${input.user_id}, ${input.name}, ${ts}, ${ts})`.raw.pipe(
        sql.withTransaction,
        Effect.orDie
      )

      const rows = yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE id = ${id}`.pipe(
        Effect.orDie
      )
      return decodeProject(rows[0] as Record<string, unknown>)
    })

    const update = Effect.fn("ProjectsRepo.update")(function* (id: ProjectId, userId: UserId, name: string) {
      const now = yield* DateTime.now
      const ts = DateTime.formatIso(now)

      // Cross-driver: confirm ownership with SELECT after UPDATE, not mutation counts.
      yield* sql`UPDATE projects SET name = ${name}, updated_at = ${ts} WHERE id = ${id} AND user_id = ${userId}`.pipe(
        Effect.orDie
      )

      const rows =
        yield* sql`SELECT id, user_id, name, created_at, updated_at FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(
          Effect.orDie
        )
      return rows[0] ? decodeProject(rows[0] as Record<string, unknown>) : null
    })

    const remove = Effect.fn("ProjectsRepo.delete")(function* (id: ProjectId, userId: UserId) {
      const before = yield* sql`SELECT id FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(Effect.orDie)
      if (before.length === 0) {
        return false
      }
      yield* sql`DELETE FROM projects WHERE id = ${id} AND user_id = ${userId}`.pipe(Effect.orDie)
      return true
    })

    return { listByUser, insert, update, delete: remove } as const
  })
)

/** Production `ProjectsRepo` backed by file SQLite. */
export const ProjectsRepoLive: Layer.Layer<ProjectsRepo, never, never> = Layer.provide(ProjectsRepoBody, [
  DatabaseLive
]) as Layer.Layer<ProjectsRepo, never, never>

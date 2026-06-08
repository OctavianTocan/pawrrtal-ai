/**
 * ProjectsService — orchestration between HTTP handlers and SQL.
 *
 * ## Where this sits
 *
 * ```text
 * Http.ts   — thin: parse request, get user id, call Service, return response
 * Service   — business rules + map repo failures to API errors  ← you are here
 * Repo.ts   — SQL only; every mutation scoped by user_id
 * ```
 *
 * Handlers in `Http.ts` should stay dumb: `yield* ProjectsService` and return the
 * result. Do not put SQL, cookie parsing, or trim/default name logic in `Http.ts`.
 *
 * ## Python parity
 *
 * Mirror `backend/app/projects/crud.py` for rules and
 * `backend/app/projects/router.py` for when to return 404:
 *
 * | Method        | Repo call              | Service job |
 * |---------------|------------------------|-------------|
 * | list          | `listByUser`           | Pass through |
 * | create        | `insert`               | `name.trim()` → empty becomes `"Untitled Project"` before insert |
 * | update        | `update`               | See update rules below; `null` from repo → `ProjectNotFoundError` |
 * | delete        | `delete`               | `false` from repo → `ProjectNotFoundError` |
 *
 * **Update rules** (match Python `update_project`, not the current Http stub):
 * - `payload.name === null` → keep existing name (fetch current row name, or read-then-write)
 * - `payload.name` provided but trims to `""` → keep existing name (do not rename to Untitled)
 * - Non-empty trimmed string → pass that string to `Repo.update`
 *
 * ## What to implement next
 *
 * 1. Fill in the method signatures on `ProjectsService` below (the second type arg
 *    to `Context.Service` — same pattern as `ProjectsRepo`).
 * 2. Add `ProjectsServiceLive`: a `Layer.effect` that `yield* ProjectsRepo` and
 *    implements each method with `Effect.fn`.
 * 3. In `Http.ts`, replace stubs with `yield* ProjectsService` and provide layers:
 *    `HttpProjectsLive.pipe(Layer.provide(ProjectsServiceLive), Layer.provide(ProjectsRepoLive))`.
 * 4. Replace `STUB_USER_ID` in `Http.ts` with a real `CurrentUser` service once auth
 *    middleware exists; Service methods always take `userId` as an explicit argument.
 *
 * ## What does NOT belong here
 *
 * - HTTP status codes → encoded on `ProjectNotFoundError` in api-core `Errors.ts`
 * - Route paths / OpenAPI → `packages/api-core/.../Api.ts`
 * - Raw SQL → `Repo.ts`
 * - JWT / cookies → future auth middleware + `CurrentUser` service
 */

import type {
	Project,
	ProjectCreateInput,
	ProjectId,
	ProjectUpdateInput,
	UserId,
} from '@pawrrtal/api-core/Modules/Projects/Domain';
import { ProjectNotFoundError } from '@pawrrtal/api-core/Modules/Projects/Errors';
import { Context, Effect, Layer } from 'effect';
import { ProjectsRepo, ProjectsRepoLive } from './Repo';

/**
 * The service class for the Projects module. It is used to define the service methods and their signatures to be used in the Http module.
 */
export class ProjectsService extends Context.Service<
	ProjectsService,
	{
		/** GET list — oldest first, same order as Python `list_projects`. */
		readonly listForUser: (userId: UserId) => Effect.Effect<ReadonlyArray<Project>>;

		/** POST create - applies trim / `"Untitled Project"` default, then inserts. */
		readonly createForUser: (
			userId: UserId,
			payload: ProjectCreateInput
		) => Effect.Effect<Project>;

		/** PATCH update - applies Python rename rules, then updates. */
		readonly updateForUser: (input: {
			userId: UserId;
			projectId: ProjectId;
			payload: ProjectUpdateInput;
		}) => Effect.Effect<Project, ProjectNotFoundError>;

		/** DELETE remove - fails with `ProjectNotFoundError` when the row is missing or not owned. */
		readonly deleteForUser: (input: {
			userId: UserId;
			projectId: ProjectId;
		}) => Effect.Effect<void, ProjectNotFoundError>;
	}
>()('@pawrrtal/api/Projects/Service') {}

/**
 * Resolve the next name for a project update. Returns the next name to use, or null if the project is not found.
 */
const resolveUpdateName = (
	projects: ReadonlyArray<Project>,
	projectId: ProjectId,
	payload: ProjectUpdateInput
): string | null => {
	if (payload.name !== null) {
		const trimmed = payload.name.trim();
		if (trimmed) {
			return trimmed;
		}
	}

	const current = projects.find((project) => project.id === projectId);
	return current?.name ?? null;
};

/**
 * Service body with no `ProjectsRepo` source attached. Production wires
 * it via {@link ProjectsServiceLive}; tests wire it with a `Ref`-backed
 * stub. See {@link ProjectsRepoBody} for the same split rationale —
 * letting tests override dependencies without fighting MemoMap.
 */
export const ProjectsServiceBody: Layer.Layer<ProjectsService, never, ProjectsRepo> = Layer.effect(
	ProjectsService,
	Effect.gen(function* () {
		const repo = yield* ProjectsRepo;

		const listForUser = Effect.fn('ProjectsService.listForUser')((userId: UserId) =>
			repo.listByUser(userId)
		);

		const createForUser = Effect.fn('ProjectService.createForUser')(function* (
			userId: UserId,
			payload: ProjectCreateInput
		) {
			const name = payload.name.trim() || 'Untitled Project';
			const project = yield* repo.insert({ name, user_id: userId });
			return project;
		});

		const updateForUser = Effect.fn('ProjectsService.updateForUser')(function* ({
			userId,
			projectId,
			payload,
		}: {
			userId: UserId;
			projectId: ProjectId;
			payload: ProjectUpdateInput;
		}) {
			const projects = yield* repo.listByUser(userId);
			const nextName = resolveUpdateName(projects, projectId, payload);
			if (nextName === null) {
				return yield* Effect.fail(new ProjectNotFoundError({ project_id: projectId }));
			}

			const updated = yield* repo.update(projectId, userId, nextName);
			if (updated === null) {
				return yield* Effect.fail(new ProjectNotFoundError({ project_id: projectId }));
			}
			return updated;
		});

		const deleteForUser = Effect.fn('ProjectsService.deleteForUser')(function* ({
			userId,
			projectId,
		}: {
			userId: UserId;
			projectId: ProjectId;
		}) {
			const deleted = yield* repo.delete(projectId, userId);
			if (!deleted) {
				return yield* Effect.fail(new ProjectNotFoundError({ project_id: projectId }));
			}
		});

		return { listForUser, createForUser, updateForUser, deleteForUser } as const;
	})
);

/** Production service layer: provides `ProjectsService` and the production `ProjectsRepo`. */
export const ProjectsServiceLive: Layer.Layer<ProjectsService, never, never> = Layer.provide(
	ProjectsServiceBody,
	[ProjectsRepoLive]
) as Layer.Layer<ProjectsService, never, never>;

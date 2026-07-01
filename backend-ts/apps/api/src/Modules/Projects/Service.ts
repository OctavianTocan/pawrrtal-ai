import type { ProjectId, UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import type { Project, ProjectCreateInput, ProjectUpdateInput } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { ProjectNotFoundError } from '@pawrrtal/api-core/Modules/Projects/Errors';
import { Context, Effect, Layer } from 'effect';
import { ProjectsRepo, ProjectsRepoLive } from './Repo';

/** Project CRUD business rules; callers pass the authenticated `userId`. */
export class ProjectsService extends Context.Service<
  ProjectsService,
  {
    readonly listForUser: (userId: UserId) => Effect.Effect<ReadonlyArray<Project>>;

    readonly createForUser: (userId: UserId, payload: ProjectCreateInput) => Effect.Effect<Project>;

    readonly updateForUser: (input: {
      userId: UserId;
      projectId: ProjectId;
      payload: ProjectUpdateInput;
    }) => Effect.Effect<Project, ProjectNotFoundError>;

    readonly deleteForUser: (input: {
      userId: UserId;
      projectId: ProjectId;
    }) => Effect.Effect<void, ProjectNotFoundError>;
  }
>()('@apps/api/Projects/Service') {}

/** Resolves the project name to persist for an update, or `null` when not found. */
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

/** `ProjectsService` without `ProjectsRepo`; wire with {@link ProjectsServiceLive} or a test repo. */
export const ProjectsServiceBody: Layer.Layer<ProjectsService, never, ProjectsRepo> = Layer.effect(
  ProjectsService,
  Effect.gen(function* () {
    const repo = yield* ProjectsRepo;

    const listForUser = Effect.fn('ProjectsService.listForUser')((userId: UserId) => repo.listByUser(userId));

    const createForUser = Effect.fn('ProjectsService.createForUser')(function* (
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
      payload
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
      projectId
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

/** Production `ProjectsService` with file-backed {@link ProjectsRepoLive}. */
export const ProjectsServiceLive: Layer.Layer<ProjectsService, never, never> = Layer.provide(ProjectsServiceBody, [
  ProjectsRepoLive
]);

import { Api } from '@pawrrtal/api-core';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { Effect, Layer } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';
import { HttpAllowedUserLive, HttpAuthLive } from '../Authentication/Http';
import { ProjectsService, ProjectsServiceLive } from './Service';

/** Live `projects` handlers — auth provides `CurrentUser`, service scopes by `user.id`. */
export const HttpProjectsLive = HttpApiBuilder.group(
  Api,
  'projects',
  Effect.fn(function* (handlers) {
    const service = yield* ProjectsService;

    return handlers
      .handle(
        'list',
        Effect.fn(function* () {
          const user = yield* CurrentUser;
          return yield* service.listForUser(user.id);
        })
      )
      .handle(
        'create',
        Effect.fn(function* ({ payload }) {
          const user = yield* CurrentUser;
          return yield* service.createForUser(user.id, payload);
        })
      )
      .handle(
        'update',
        Effect.fn(function* ({ params, payload }) {
          const user = yield* CurrentUser;
          return yield* service.updateForUser({
            userId: user.id,
            projectId: params.project_id,
            payload
          });
        })
      )
      .handle(
        'delete',
        Effect.fn(function* ({ params }) {
          const user = yield* CurrentUser;
          return yield* service.deleteForUser({
            userId: user.id,
            projectId: params.project_id
          });
        })
      );
  })
  // Auth middleware is a handler-layer dependency, not a sibling in `Effect.provide`.
).pipe(Layer.provide([ProjectsServiceLive, HttpAuthLive, HttpAllowedUserLive]));

import { Api } from '@pawrrtal/api-core';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { Effect, Layer } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';
import { HttpAllowedUserLive, HttpAuthLive } from '../Authentication/Http';
import { ConversationsService, ConversationsServiceLive } from './Service';

/** Live `conversations` handlers — auth provides `CurrentUser`, service scopes by `user.id`. */
export const HttpConversationsLive = HttpApiBuilder.group(
  Api,
  'conversations',
  Effect.fn(function* (handlers) {
    const service = yield* ConversationsService;
    return handlers
      .handle(
        'list',
        Effect.fn(function* () {
          const user = yield* CurrentUser;
          return yield* service.list(user.id);
        })
      )
      .handle(
        'create',
        Effect.fn(function* ({ payload }) {
          const user = yield* CurrentUser;
          return yield* service.create(user.id, payload);
        })
      )
      .handle(
        'get',
        Effect.fn(function* ({ params }) {
          const user = yield* CurrentUser;
          return yield* service.get(user.id, params.conversation_id);
        })
      )
      .handle(
        'update',
        Effect.fn(function* ({ params, payload }) {
          const user = yield* CurrentUser;
          return yield* service.update(user.id, params.conversation_id, payload);
        })
      )
      .handle(
        'remove',
        Effect.fn(function* ({ params }) {
          const user = yield* CurrentUser;
          return yield* service.remove(user.id, params.conversation_id);
        })
      )
      .handle(
        'messages',
        Effect.fn(function* ({ params }) {
          const user = yield* CurrentUser;
          return yield* service.getMessages(user.id, params.conversation_id);
        })
      );
  })
).pipe(Layer.provide([ConversationsServiceLive, HttpAuthLive, HttpAllowedUserLive]));

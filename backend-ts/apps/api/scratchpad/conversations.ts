import { BunRuntime } from '@effect/platform-bun';
import { Ids } from '@pawrrtal/api-core/Lib/TypeIds';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { Console, Effect, Layer } from 'effect';
import { ConversationsService, ConversationsServiceLive } from '../src/Modules/Conversations/Service';

const program = Effect.gen(function* () {
  const service = yield* ConversationsService;
  const user = yield* CurrentUser;
  const conversation = yield* service.create(user.id, {
    id: Ids.conversation.make('00000000-0000-4000-8000-000000000001'),
    title: 'Test Conversation'
  });
  yield* Console.log(conversation);
}).pipe(Effect.provide(Layer.mergeAll(ConversationsServiceLive, CurrentUser.Test)));

BunRuntime.runMain(program);

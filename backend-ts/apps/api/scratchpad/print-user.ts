import { CurrentUser } from '@pawrrtal/api-core/Modules/Authentication/Domain';
import { Console, Effect } from 'effect';

const program = Effect.gen(function* () {
	const user = yield* CurrentUser;
	yield* Console.log(`User: ${user.name} (${user.email})`);
}).pipe(Effect.provide(CurrentUser.Test));

Effect.runPromise(program);

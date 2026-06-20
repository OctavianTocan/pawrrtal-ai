import { Console, Effect } from 'effect';
import { SessionStore, SessionStoreLive } from '../src/Modules/Auth/SessionStore';

const program = Effect.gen(function* () {
	const sessionStore = yield* SessionStore;
	const user = yield* sessionStore.lookup('test');
	yield* Console.log(user);
}).pipe(Effect.provide(SessionStoreLive));
Effect.runPromise(program);

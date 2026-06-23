/** Scratchpad: print `CurrentUser.Test` fixture. Run: `bun run scratchpad/print-user.ts` */

import { BunRuntime } from '@effect/platform-bun';
import { CurrentUser } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { Console, Effect } from 'effect';

const program = Effect.gen(function* () {
	const user = yield* CurrentUser;
	yield* Console.log(`User: ${user.email} (${user.id})`);
}).pipe(Effect.provide(CurrentUser.Test));

BunRuntime.runMain(program);

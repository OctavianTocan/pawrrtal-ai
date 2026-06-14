/**
 * Lesson 1 scratchpad — proves the `CurrentUser` service kernel works.
 *
 * Reads `CurrentUser.Test` (the hard-coded fixture layer) and prints
 * the user's name + email. Run with:
 *
 *   cd backend-ts/apps/api && bun run scratchpad/print-user.ts
 *
 * Expected output: `User: John Doe (john@doe.com)`.
 */

import { CurrentUser } from '@pawrrtal/api-core/Modules/Authentication/Domain';
import { Console, Effect } from 'effect';

const program = Effect.gen(function* () {
	const user = yield* CurrentUser;
	yield* Console.log(`User: ${user.name} (${user.email})`);
}).pipe(Effect.provide(CurrentUser.Test));

Effect.runPromise(program);

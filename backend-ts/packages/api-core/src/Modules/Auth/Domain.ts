/**
 * Authentication module — domain types and the `CurrentUser` service.
 *
 * The `CurrentUser` service is the *contract* for "the authenticated
 * user who hit this request." It is *populated* by the auth middleware
 * (Lesson 3, see `Authentication/Api.ts`) and *consumed* by every
 * handler that needs the request's user identity (Lesson 4, e.g.
 * `Projects/Http.ts` swapping its `STUB_USER_ID` for `yield* CurrentUser`).
 *
 * Comcom (v3) ancestor: `backend/vendor/comcom/packages/comcom/api-core/
 * src/Modules/Authentication/Domain.ts:58-119` — same idea, the class
 * is `AuthContext` and the shape is wider. v4 collapsed the bare
 * `Context.Tag` form into the class-form `Context.Service`.
 */

import { Context, Layer, Schema } from 'effect';
import { UserId } from '../Projects/Domain';

const Email = Schema.String.check(Schema.isPattern(/^[^\s@]+@[^\s@]+\.[^\s@]+$/));

/**
 * The user entity.
 * Used in the `CurrentUser` service.
 */
export class User extends Schema.Class<User>('User')({
	id: UserId,
	email: Email,
	isActive: Schema.Boolean,
	isSuperuser: Schema.Boolean,
	isVerified: Schema.Boolean,
}) {}

/**
 * The currently authenticated user, populated by the auth middleware
 * (Lesson 3) and `yield*`-consumed by handlers. `Test` is the
 * hard-coded layer for scratchpads, unit tests, and dev tooling;
 * `Live` (the runtime layer, populated by the middleware) lands in
 * Lesson 3.
 */
export class CurrentUser extends Context.Service<CurrentUser, User>()(
	'@apps/api/Auth/CurrentUser'
) {
	/**
	 * Hard-coded fixture layer — used by scratchpads, unit tests, and
	 * dev tooling. Not the production implementation; the runtime
	 * `Live` layer arrives in Lesson 3 alongside the middleware.
	 */
	static readonly Test = Layer.succeed(
		CurrentUser,
		new User({
			id: UserId.make('00000000-0000-4000-8000-000000000001'),
			email: 'john@doe.com',
			isActive: true,
			isSuperuser: false,
			isVerified: true,
		})
	);
}

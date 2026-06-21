import { Context, Layer, Schema } from 'effect';
import { UserId } from '../Projects/Domain';

const Email = Schema.String.check(Schema.isPattern(/^[^\s@]+@[^\s@]+\.[^\s@]+$/));

/**
 * The user entity.
 * Used in the `CurrentUser` service.
 */
export class User extends Schema.Class<User>('User')({
	id: UserId,
	name: Schema.String.check(Schema.isMinLength(1)),
	email: Email,
}) {}

export class CurrentUser extends Context.Service<CurrentUser, User>()(
	'@apps/api/Auth/CurrentUser'
) {
	/**
	 * Not entirely sure what this is for.
	 */
	static readonly Test = Layer.succeed(
		CurrentUser,
		new User({
			id: UserId.make('00000000-0000-4000-8000-000000000001'),
			name: 'John Doe',
			email: 'john@doe.com',
		})
	);
}

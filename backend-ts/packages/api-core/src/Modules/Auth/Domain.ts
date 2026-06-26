import { Context, Layer, Schema } from "effect"
import { UserId } from "../Projects/Domain"

const Email = Schema.String.check(Schema.isPattern(/^[^\s@]+@[^\s@]+\.[^\s@]+$/))

export class User extends Schema.Class<User>("User")({
  id: UserId,
  email: Email,
  is_active: Schema.Boolean,
  is_superuser: Schema.Boolean,
  is_verified: Schema.Boolean
}) {}

/** Authenticated user for the current request; populated by auth middleware. */
export class CurrentUser extends Context.Service<CurrentUser, User>()("@apps/api/Auth/CurrentUser") {
  /** Test fixture — do not merge into `CoreModulesLive`. */
  static readonly Test = Layer.succeed(
    CurrentUser,
    new User({
      id: UserId.make("00000000-0000-4000-8000-000000000001"),
      email: "john@doe.com",
      is_active: true,
      is_superuser: false,
      is_verified: true
    })
  )
}

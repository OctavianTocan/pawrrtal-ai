import { BunRuntime } from "@effect/platform-bun"
import { Console, Effect } from "effect"
import { SessionStore, SessionStoreLive } from "../src/Modules/Authentication/SessionStore"

const program = Effect.gen(function* () {
  const sessionStore = yield* SessionStore
  const user = yield* sessionStore.lookup("test")
  yield* Console.log(user)
}).pipe(Effect.provide(SessionStoreLive))
BunRuntime.runMain(program)

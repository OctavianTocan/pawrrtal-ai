import { Layer } from "effect"
import { HttpConversationsLive } from "./Conversations/Http"
import { HttpProjectsLive } from "./Projects/Http"
import { HttpSystemLive } from "./System/Http"

/** Merged runtime layers for every non-admin HttpApi group. */
export const CoreModulesLive = Layer.mergeAll(HttpSystemLive, HttpProjectsLive, HttpConversationsLive)

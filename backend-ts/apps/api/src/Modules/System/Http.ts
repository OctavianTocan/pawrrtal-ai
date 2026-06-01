import { Effect } from "effect"
import { HttpApiBuilder } from "effect/unstable/httpapi"
import { PawrrtalApi } from "@pawrrtal/api-core"

export const HttpSystemLive = HttpApiBuilder.group(
    PawrrtalApi,
    "pawrrtal-system",
    Effect.fn(function* (handlers) {
        // This returns "success, no content"
        return handlers.handle("health", () => Effect.void)
    })
)
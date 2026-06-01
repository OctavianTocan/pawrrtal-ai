import { Layer } from "effect";
import { HttpSystemLive } from "./System/Http";

// Merged HTTP handler layers, so we don't have to import each one individually.
export const CoreModulesLive = Layer.mergeAll(
    HttpSystemLive
)
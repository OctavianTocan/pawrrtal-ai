import { HttpApi } from "effect/unstable/httpapi";
import { PawrrtalSystemApi } from "./Modules/System/SystemApi";

// This is the root API for the Pawrrtal platform.
export class PawrrtalApi extends HttpApi.make("api").add(PawrrtalSystemApi) {}
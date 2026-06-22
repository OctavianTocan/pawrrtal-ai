/**
 * `CoreModulesLive` — the merged runtime layer for every non-admin
 * HttpApi group.
 *
 * Add a new module's `Http<Name>Live` here when you ship a new group;
 * `App.ts` will pick it up automatically via `Layer.provide(CoreModulesLive)`.
 */

import { Layer } from 'effect';
import { HttpAuthLive } from './Authentication/Http';
import { HttpProjectsLive } from './Projects/Http';
import { HttpSystemLive } from './System/Http';
/**
 * Every HttpApi group's runtime implementation, merged into one layer
 * so `App.ts` only has to provide a single dependency. Admin-only groups
 * (when they land) belong in a parallel `AdminModulesLive`.
 */
export const CoreModulesLive = Layer.mergeAll(HttpSystemLive, HttpProjectsLive, HttpAuthLive);

/**
 * HTTP integration tests for `Projects` (real wire test).
 *
 * **Status: deferred.** The real-port integration test using
 * `HttpApiClient.make(Api, { baseUrl })` against `BunHttpServer.layerTest`
 * is tracked separately; the canonical, working HTTP-shape coverage lives
 * in `test/unit/Modules/Projects/Http.test.ts` which uses
 * `HttpApiTest.groups(Api, ['projects'])` and runs the same handler
 * stubs over a synthesized in-memory client. The real-port variant is
 * blocked on:
 *
 * - `HttpApiClient.make` payload encoding for `Schema.Class`-typed
 *   payloads (e.g. `ProjectCreateInput`) — current v4 behavior wraps the
 *   caller's plain object in an `Option` and rejects it during the
 *   transformation Link (`actual: { _id: 'Option', _tag: 'Some', ... }`).
 *   Either encode the payload manually with
 *   `Schema.encodeUnknown(ProjectCreateInput)({ name })` before calling
 *   `client.projects.create`, or switch to the raw `HttpClient` path.
 * - Confirming `BunHttpServer.layerTest` propagates `HttpServer.address`
 *   to user code under the `it.effect` scope. The platform-node
 *   `HttpApi.test.ts` example uses `Effect.provide(ApiLive)` per test
 *   (not the `layer(...)` from `@effect/vitest`); the Bun equivalent
 *   needs the same plumbing.
 *
 * This file is a placeholder so the WIP tree shape
 * (`test/Modules/Projects/{Http,Repo,Service}.test.ts`) lands in git
 * while the real-port test is moved to a follow-up.
 */
import { describe, it } from '@effect/vitest';
import { assert } from 'effect';

describe('Projects HTTP (in-memory, real port)', () => {
	it.skip('is covered by test/unit/Modules/Projects/Http.test.ts; see file header', () => {
		assert.isTrue(true);
	});
});

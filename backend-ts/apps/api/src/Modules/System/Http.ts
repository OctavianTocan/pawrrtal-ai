/**
 * `System` HTTP group — runtime handler for the SystemApi group.
 *
 * Currently a single `health` endpoint that returns 204 No Content.
 * Wired into the app via `CoreModulesLive` (`Modules/Layers.ts`).
 */

import { Api } from '@pawrrtal/api-core';
import { Effect } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';

/** Live implementation of the `system` group. Liveness check only. */
export const HttpSystemLive = HttpApiBuilder.group(
	Api,
	'system',
	Effect.fn(function* (handlers) {
		// This returns "success, no content"
		return handlers.handle('health', () => Effect.void);
	})
);

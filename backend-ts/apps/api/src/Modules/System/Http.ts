import { Effect } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';
import { Api } from '@pawrrtal/api-core';

export const HttpSystemLive = HttpApiBuilder.group(
	Api,
	'system',
	Effect.fn(function* (handlers) {
		// This returns "success, no content"
		return handlers.handle('health', () => Effect.void);
	})
);

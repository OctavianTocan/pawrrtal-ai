import { Api } from '@pawrrtal/api-core';
import { Effect } from 'effect';
import { HttpApiBuilder } from 'effect/unstable/httpapi';

/** Live `system` handlers. */
export const HttpSystemLive = HttpApiBuilder.group(
  Api,
  'system',
  Effect.fn(function* (handlers) {
    return handlers.handle('health', () => Effect.void);
  })
);

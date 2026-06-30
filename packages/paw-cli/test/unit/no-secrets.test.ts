import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import { validateNoSecrets } from '../../src/Helpers/Config';

describe('no-secret config validation', (): void => {
  it.effect(
    'accepts ordinary profile settings',
    (): Effect.Effect<void> =>
      validateNoSecrets({
        profile: 'local',
        backendUrl: 'http://localhost:8000',
      }).pipe(
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Success');
          return undefined;
        })
      )
  );

  it.effect(
    'rejects nested token-like fields',
    (): Effect.Effect<void> =>
      validateNoSecrets({
        auth: {
          accessToken: 'secret',
        },
      }).pipe(
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Failure');
          return undefined;
        })
      )
  );
});

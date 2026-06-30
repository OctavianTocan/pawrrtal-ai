import { BunServices } from '@effect/platform-bun';
import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import { validateNoSecrets, writeProfileConfig } from '../../src/Helpers/Config';

describe('no-secret config validation', (): void => {
  it.effect(
    'accepts ordinary profile settings',
    (): Effect.Effect<void> =>
      validateNoSecrets({
        profile: 'local',
        backendUrl: 'http://localhost:8000',
        ssh_public_key: 'public',
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

  it.effect(
    'rejects common key-like secret field names',
    (): Effect.Effect<void> =>
      validateNoSecrets({
        auth: {
          access_key: 'secret',
          private_key: 'secret',
        },
      }).pipe(
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Failure');
          return undefined;
        })
      )
  );

  it.effect(
    'rejects profile names that would write outside the profile directory',
    (): Effect.Effect<void> =>
      writeProfileConfig({
        profile: '../outside',
        configRoot: `/tmp/paw-cli-profile-write-${crypto.randomUUID()}`,
        values: { backendUrl: 'http://localhost:8000' },
      }).pipe(
        Effect.provide(BunServices.layer),
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Failure');
          return undefined;
        })
      )
  );
});

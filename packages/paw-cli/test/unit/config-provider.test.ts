import { describe, expect, it } from '@effect/vitest';
import { Effect, Option } from 'effect';
import { readEnvironmentOverrides } from '../../src/Helpers/Config';

describe('environment override config provider', (): void => {
  it.effect(
    'decodes supported environment values through Effect ConfigProvider',
    (): Effect.Effect<void> =>
      readEnvironmentOverrides({
        PAW_HOME: '  ',
        PAW_PROFILE: 'local',
        PAW_BACKEND_URL: 'http://localhost:8000',
        XDG_CONFIG_HOME: '/tmp/config',
        XDG_CACHE_HOME: '/tmp/cache',
      }).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Success');
            if (exit._tag === 'Success') {
              expect(exit.value.pawHome).toEqual(Option.none());
              expect(exit.value.pawProfile).toEqual(Option.some('local'));
              expect(exit.value.pawBackendUrl).toEqual(Option.some('http://localhost:8000'));
              expect(exit.value.xdgConfigHome).toEqual(Option.some('/tmp/config'));
              expect(exit.value.xdgCacheHome).toEqual(Option.some('/tmp/cache'));
            }
          })
        ),
        Effect.asVoid
      )
  );

  it.effect(
    'does not read from the real process environment in tests',
    (): Effect.Effect<void> =>
      readEnvironmentOverrides({}).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Success');
            if (exit._tag === 'Success') {
              expect(exit.value).toEqual({
                pawHome: Option.none(),
                pawProfile: Option.none(),
                pawBackendUrl: Option.none(),
                xdgConfigHome: Option.none(),
                xdgCacheHome: Option.none(),
              });
            }
          })
        ),
        Effect.asVoid
      )
  );
});

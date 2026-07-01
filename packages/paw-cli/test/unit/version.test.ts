import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import { CLI_VERSION, decodePackageManifestSummary } from '../../src/Helpers/Version';

describe('package manifest boundary', (): void => {
  it('uses the decoded package version as the CLI version', (): void => {
    expect(CLI_VERSION).toBe('0.1.0');
  });

  it.effect(
    'decodes a valid package manifest summary',
    (): Effect.Effect<void> =>
      decodePackageManifestSummary({ version: '1.2.3' }).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Success');
            if (exit._tag === 'Success') {
              expect(exit.value.version).toBe('1.2.3');
            }
          })
        ),
        Effect.asVoid
      )
  );

  it.effect(
    'rejects missing or non-string package versions',
    (): Effect.Effect<void> =>
      Effect.all([
        decodePackageManifestSummary({}).pipe(Effect.exit),
        decodePackageManifestSummary({ version: 123 }).pipe(Effect.exit),
      ]).pipe(
        Effect.tap(([missing, wrongType]) =>
          Effect.sync(() => {
            expect(missing._tag).toBe('Failure');
            expect(wrongType._tag).toBe('Failure');
          })
        ),
        Effect.asVoid
      )
  );
});

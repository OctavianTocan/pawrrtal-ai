import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import { validateCommandMetadata } from '../../src/Helpers/CommandMetadata';
import { ContextCommand } from '../../src/Modules/Context/Command';

describe('command metadata boundary', (): void => {
  it.effect(
    'accepts source-owned command metadata',
    (): Effect.Effect<void> =>
      validateCommandMetadata(ContextCommand.metadata).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Success');
            if (exit._tag === 'Success') {
              expect(exit.value.name).toBe('context');
              expect(exit.value.outputModes).toContain('json');
            }
          })
        ),
        Effect.asVoid
      )
  );

  it.effect(
    'rejects metadata with missing required public fields',
    (): Effect.Effect<void> =>
      validateCommandMetadata({
        name: 'broken',
        summary: '',
        description: 'Broken command metadata.',
        owner: '@pawrrtal/cli/test',
        outputModes: ['human'],
      }).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Failure');
          })
        ),
        Effect.asVoid
      )
  );
});

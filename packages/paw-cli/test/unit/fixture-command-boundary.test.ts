import { describe, expect, it } from '@effect/vitest';
import { Effect, Schema } from 'effect';
import { formatOutput } from '../../src/Helpers/Output';
import { fixtureFormatters } from '../fixtures/FixtureCommand';

describe('fixture command boundary contract', (): void => {
  it.effect(
    'encodes a valid future command fixture output',
    (): Effect.Effect<void> =>
      formatOutput({ name: 'fixture', ok: true }, 'json', fixtureFormatters).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Success');
            if (exit._tag === 'Success') {
              expect(JSON.parse(exit.value)).toEqual({ name: 'fixture', ok: true });
            }
          })
        ),
        Effect.asVoid
      )
  );

  it.effect('fails when a schema refinement rejects rendered output', (): Effect.Effect<void> => {
    const refinedFormatters = {
      human: (value: { readonly status: string }): string => value.status,
      json: {
        schema: Schema.Struct({
          status: Schema.String.check(Schema.isPattern(/^ok$/)),
        }),
        render: (value: { readonly status: string }): { readonly status: string } => value,
      },
    };

    return formatOutput({ status: 'bad' }, 'json', refinedFormatters).pipe(
      Effect.exit,
      Effect.tap((exit) =>
        Effect.sync(() => {
          expect(exit._tag).toBe('Failure');
        })
      ),
      Effect.asVoid
    );
  });
});

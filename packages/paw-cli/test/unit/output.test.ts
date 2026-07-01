import { describe, expect, it } from '@effect/vitest';
import { Effect, Schema } from 'effect';
import { formatOutput, resolveOutputMode } from '../../src/Helpers/Output';

describe('output helpers', (): void => {
  it.effect(
    'rejects conflicting automation modes',
    (): Effect.Effect<void> =>
      resolveOutputMode({ json: true, plain: true }).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Failure');
          })
        ),
        Effect.asVoid
      )
  );

  it.effect('formats human, JSON, and plain output through declared schemas', (): Effect.Effect<void> => {
    const value = { name: 'context', status: 'ok' } as const;
    const formatters = {
      human: (input: typeof value): string => `${input.name}: ${input.status}`,
      json: {
        schema: Schema.Struct({ name: Schema.String, status: Schema.Literal('ok') }),
        render: (input: typeof value): typeof value => input,
      },
      plain: (input: typeof value): string => `${input.name}\t${input.status}`,
    };

    return Effect.all([
      formatOutput(value, 'human', formatters),
      formatOutput(value, 'json', formatters),
      formatOutput(value, 'plain', formatters),
    ]).pipe(
      Effect.exit,
      Effect.tap((exit) =>
        Effect.sync(() => {
          expect(exit._tag).toBe('Success');
          if (exit._tag === 'Success') {
            const [human, json, plain] = exit.value;
            expect(human).toBe('context: ok');
            expect(json).toContain('"status": "ok"');
            expect(plain).toBe('context\tok');
          }
        })
      ),
      Effect.asVoid
    );
  });

  it.effect(
    'fails when structured output does not match its schema',
    (): Effect.Effect<void> =>
      formatOutput({ status: 'bad' }, 'json', {
        human: (value): string => value.status,
        json: {
          schema: Schema.Struct({
            status: Schema.String.check(Schema.isPattern(/^ok$/)),
          }),
          render: (value): { readonly status: string } => value,
        },
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

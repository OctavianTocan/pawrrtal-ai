import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import { formatOutput, resolveOutputMode } from '../../src/Helpers/Output';

describe('output helpers', (): void => {
  it.effect(
    'rejects conflicting automation modes',
    (): Effect.Effect<void> =>
      resolveOutputMode({ json: true, plain: true }).pipe(
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Failure');
          return undefined;
        })
      )
  );

  it('formats human, JSON, and plain output', (): void => {
    const value = { name: 'context', status: 'ok' };
    const formatters = {
      human: (input: typeof value): string => `${input.name}: ${input.status}`,
      json: (input: typeof value): unknown => input,
      plain: (input: typeof value): string => `${input.name}\t${input.status}`,
    };

    expect(formatOutput(value, 'human', formatters)).toBe('context: ok');
    expect(formatOutput(value, 'json', formatters)).toContain('"status": "ok"');
    expect(formatOutput(value, 'plain', formatters)).toBe('context\tok');
  });
});

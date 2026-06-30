import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import type { UsageError } from '../../src/Helpers/Errors';
import { resolveBodySource } from '../../src/Helpers/InputSource';

describe('input source policy', (): void => {
  it.effect(
    'selects one explicit body source',
    (): Effect.Effect<void, UsageError> =>
      resolveBodySource({ file: 'body.md' }).pipe(
        Effect.map((result) => {
          expect(result).toEqual({ _tag: 'Selected', source: { kind: 'file', value: 'body.md' } });
          return undefined;
        })
      )
  );

  it.effect(
    'treats file path dash as stdin',
    (): Effect.Effect<void, UsageError> =>
      resolveBodySource({ file: '-' }).pipe(
        Effect.map((result) => {
          expect(result).toEqual({ _tag: 'Selected', source: { kind: 'stdin', value: '-' } });
          return undefined;
        })
      )
  );

  it.effect(
    'rejects ambiguous body sources',
    (): Effect.Effect<void> =>
      resolveBodySource({ file: 'body.md', inline: 'hello' }).pipe(
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Failure');
          return undefined;
        })
      )
  );

  it.effect(
    'rejects editor fallback outside an interactive terminal',
    (): Effect.Effect<void> =>
      resolveBodySource({ isEditorRequested: true, isInteractive: false }).pipe(
        Effect.exit,
        Effect.map((exit) => {
          expect(exit._tag).toBe('Failure');
          return undefined;
        })
      )
  );
});

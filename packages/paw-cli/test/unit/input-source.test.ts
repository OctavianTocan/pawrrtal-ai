import { describe, expect, it } from '@effect/vitest';
import { Effect, Option } from 'effect';
import type { UsageError } from '../../src/Helpers/Errors';
import { EmptyBodySourceOptions, resolveBodySource } from '../../src/Helpers/InputSource';
import { FixtureCommand } from '../fixtures/FixtureCommand';

describe('input source policy', (): void => {
  it.effect(
    'selects one explicit body source',
    (): Effect.Effect<void, UsageError> =>
      resolveBodySource({ ...EmptyBodySourceOptions, file: Option.some('body.md') }).pipe(
        Effect.tap((result) =>
          Effect.sync(() => {
            expect(result).toEqual({ _tag: 'Selected', source: { kind: 'file', value: 'body.md' } });
          })
        ),
        Effect.asVoid
      )
  );

  it.effect(
    'treats file path dash as stdin',
    (): Effect.Effect<void, UsageError> =>
      resolveBodySource({ ...EmptyBodySourceOptions, file: Option.some('-') }).pipe(
        Effect.tap((result) =>
          Effect.sync(() => {
            expect(result).toEqual({ _tag: 'Selected', source: { kind: 'stdin', value: '-' } });
          })
        ),
        Effect.asVoid
      )
  );

  it.effect(
    'rejects ambiguous body sources',
    (): Effect.Effect<void> =>
      resolveBodySource({
        ...EmptyBodySourceOptions,
        file: Option.some('body.md'),
        inline: Option.some('hello'),
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

  it.effect(
    'rejects editor fallback outside an interactive terminal',
    (): Effect.Effect<void> =>
      resolveBodySource({ ...EmptyBodySourceOptions, isEditorRequested: true, isInteractive: false }).pipe(
        Effect.exit,
        Effect.tap((exit) =>
          Effect.sync(() => {
            expect(exit._tag).toBe('Failure');
          })
        ),
        Effect.asVoid
      )
  );

  it('is represented in command metadata for generated guidance', (): void => {
    expect(FixtureCommand.metadata.inputSources).toEqual(['inline', 'file', 'stdin', 'editor']);
  });
});

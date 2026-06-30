import { describe, expect, it } from '@effect/vitest';
import { Effect } from 'effect';
import type { RegisteredCommandModule } from '../../src/Commands';
import { makeCommandRegistry, validateCommandRegistry } from '../../src/Commands';
import { ContextCommand } from '../../src/Modules/Context/Command';
import { FixtureCommand } from '../fixtures/FixtureCommand';

describe('command registry conflicts', (): void => {
  it.effect('rejects duplicate command names', (): Effect.Effect<void> => {
    const registry = makeCommandRegistry([ContextCommand, ContextCommand]);
    return validateCommandRegistry(registry).pipe(
      Effect.exit,
      Effect.map((exit) => {
        expect(exit._tag).toBe('Failure');
        return undefined;
      })
    );
  });

  it.effect('rejects aliases that conflict with another command name', (): Effect.Effect<void> => {
    const conflictingCommand = makeAliasConflictCommand();
    const registry = makeCommandRegistry([ContextCommand, conflictingCommand]);
    return validateCommandRegistry(registry).pipe(
      Effect.exit,
      Effect.map((exit) => {
        expect(exit._tag).toBe('Failure');
        return undefined;
      })
    );
  });
});

/** Builds a fixture command whose alias collides with a built-in command. */
function makeAliasConflictCommand(): RegisteredCommandModule {
  return {
    ...FixtureCommand,
    metadata: {
      ...FixtureCommand.metadata,
      aliases: ['context'],
    },
  };
}

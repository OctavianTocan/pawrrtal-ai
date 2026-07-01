import { describe, expect, it } from '@effect/vitest';
import { DefaultCommandRegistry, makeCommandRegistry } from '../../src/Commands';
import { ContextCommand } from '../../src/Modules/Context/Command';
import { FixtureCommand } from '../fixtures/FixtureCommand';

describe('command registry', (): void => {
  it('registers the built-in command surface plus completions', (): void => {
    const commandNames = DefaultCommandRegistry.modules.map((module) => module.metadata.name);

    expect(commandNames).toEqual(['doctor', 'context', 'completions']);
  });

  it('registers a feature-owned fixture through the same metadata path', (): void => {
    const registry = makeCommandRegistry([ContextCommand, FixtureCommand]);
    const commandNames = registry.modules.map((module) => module.metadata.name);
    const rootCommandNames = registry.rootMetadata.subcommands?.map((command) => command.name);

    expect(commandNames).toEqual(['context', 'fixture', 'completions']);
    expect(rootCommandNames).toEqual(['context', 'fixture', 'completions']);
  });

  it('keeps structured output metadata on feature-owned commands', (): void => {
    const registry = makeCommandRegistry([FixtureCommand]);
    const fixtureMetadata = registry.rootMetadata.subcommands?.find((command) => command.name === 'fixture');

    expect(fixtureMetadata?.structuredOutputs).toEqual([
      {
        mode: 'json',
        contract: 'FixtureOutput',
        description: 'Test-only structured output contract for future command modules.',
      },
    ]);
  });
});

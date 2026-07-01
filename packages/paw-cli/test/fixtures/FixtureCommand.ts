import { Schema } from 'effect';
import { Command } from 'effect/unstable/cli';
import type { RegisteredCommandModule } from '../../src/Commands';
import type { CommandMetadata } from '../../src/Helpers/CommandMetadata';
import { applyCommandMetadata } from '../../src/Helpers/CommandMetadata';
import { ExitCode } from '../../src/Helpers/ExitCode';
import type { Formatters } from '../../src/Helpers/Output';

export const FixtureOutputSchema = Schema.Struct({
  name: Schema.Literal('fixture'),
  ok: Schema.Boolean,
});

export type FixtureOutput = {
  readonly name: 'fixture';
  readonly ok: boolean;
};

export const FIXTURE_METADATA = {
  name: 'fixture',
  summary: 'Exercise feature-owned command registration',
  description: 'Exercise feature-owned command registration in tests.',
  owner: '@pawrrtal/cli/test',
  aliases: ['fx'],
  outputModes: ['human', 'json'],
  structuredOutputs: [
    {
      mode: 'json',
      contract: 'FixtureOutput',
      description: 'Test-only structured output contract for future command modules.',
    },
  ],
  inputSources: ['inline', 'file', 'stdin', 'editor'],
  exitCodes: [ExitCode.success],
} satisfies CommandMetadata;

export const fixtureFormatters: Formatters<FixtureOutput, typeof FixtureOutputSchema> = {
  human: (value): string => `${value.name}: ${String(value.ok)}`,
  json: {
    schema: FixtureOutputSchema,
    render: (value): FixtureOutput => value,
  },
};

/** Test-only command module that acts like a future feature-owned command. */
export const FixtureCommand = {
  command: applyCommandMetadata(Command.make('fixture').pipe(Command.withAlias('fx')), FIXTURE_METADATA),
  metadata: FIXTURE_METADATA,
} satisfies RegisteredCommandModule;

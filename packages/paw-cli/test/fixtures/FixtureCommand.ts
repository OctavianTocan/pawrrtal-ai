import { Command } from 'effect/unstable/cli';
import type { RegisteredCommandModule } from '../../src/Commands';
import type { CommandMetadata } from '../../src/Helpers/CommandMetadata';
import { ExitCode } from '../../src/Helpers/ExitCode';

export const FIXTURE_METADATA = {
  name: 'fixture',
  summary: 'Exercise feature-owned command registration',
  description: 'Exercise feature-owned command registration in tests.',
  owner: '@pawrrtal/cli/test',
  aliases: ['fx'],
  outputModes: ['human'],
  exitCodes: [ExitCode.success],
} satisfies CommandMetadata;

/** Test-only command module that acts like a future feature-owned command. */
export const FixtureCommand = {
  command: Command.make('fixture').pipe(
    Command.withAlias('fx'),
    Command.withDescription(FIXTURE_METADATA.description),
    Command.withShortDescription(FIXTURE_METADATA.summary)
  ),
  metadata: FIXTURE_METADATA,
} satisfies RegisteredCommandModule;

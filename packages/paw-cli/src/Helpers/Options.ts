import type { Option } from 'effect';
import type { Command as CliCommand } from 'effect/unstable/cli';
import { Flag } from 'effect/unstable/cli';
import { AUTOMATION_FLAG_METADATA, GLOBAL_FLAG_METADATA } from './CommandMetadata';

export type RootOptions = {
  readonly profile: Option.Option<string>;
  readonly backendUrl: Option.Option<string>;
  readonly verbose: boolean;
};

export type AutomationOptions = {
  readonly json: boolean;
  readonly plain: boolean;
};

/** Shared flags available at the root and every subcommand. */
export const rootSharedFlags = {
  profile: Flag.string('profile').pipe(
    Flag.optional,
    Flag.withDescription(flagDescription('profile', GLOBAL_FLAG_METADATA))
  ),
  backendUrl: Flag.string('backend-url').pipe(
    Flag.optional,
    Flag.withDescription(flagDescription('backend-url', GLOBAL_FLAG_METADATA))
  ),
  verbose: Flag.boolean('verbose').pipe(
    Flag.withDefault(false),
    Flag.withDescription(flagDescription('verbose', GLOBAL_FLAG_METADATA))
  ),
} as const satisfies CliCommand.Command.FlagConfig;

/** Automation output flags reused by commands that print structured data. */
export const automationFlags = {
  json: Flag.boolean('json').pipe(
    Flag.withDefault(false),
    Flag.withDescription(flagDescription('json', AUTOMATION_FLAG_METADATA))
  ),
  plain: Flag.boolean('plain').pipe(
    Flag.withDefault(false),
    Flag.withDescription(flagDescription('plain', AUTOMATION_FLAG_METADATA))
  ),
} as const satisfies CliCommand.Command.FlagConfig;

/** Reads a flag description from the canonical metadata list. */
function flagDescription(
  name: string,
  metadata: ReadonlyArray<{ readonly name: string; readonly description: string }>
): string {
  return metadata.find((flag) => flag.name === name)?.description ?? name;
}

import type { Option } from 'effect';
import type { Command as CliCommand } from 'effect/unstable/cli';
import { Flag } from 'effect/unstable/cli';

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
    Flag.withDescription('Run this invocation against a specific profile')
  ),
  backendUrl: Flag.string('backend-url').pipe(
    Flag.optional,
    Flag.withDescription('Run this invocation against a specific backend target')
  ),
  verbose: Flag.boolean('verbose').pipe(
    Flag.withDefault(false),
    Flag.withDescription('Print expanded diagnostics and source chains')
  ),
} as const satisfies CliCommand.Command.FlagConfig;

/** Automation output flags reused by commands that print structured data. */
export const automationFlags = {
  json: Flag.boolean('json').pipe(Flag.withDefault(false), Flag.withDescription('Print structured JSON to stdout')),
  plain: Flag.boolean('plain').pipe(
    Flag.withDefault(false),
    Flag.withDescription('Print tab-separated values to stdout with no headers')
  ),
} as const satisfies CliCommand.Command.FlagConfig;

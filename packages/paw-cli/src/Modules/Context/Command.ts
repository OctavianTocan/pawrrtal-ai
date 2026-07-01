import { Console, Effect } from 'effect';
import { Command } from 'effect/unstable/cli';
import type { CommandMetadata, CommandModule, EmptyCommandContext } from '../../Helpers/CommandMetadata';
import { AUTOMATION_FLAG_METADATA, applyCommandMetadata } from '../../Helpers/CommandMetadata';
import type { UsageError, VerificationError } from '../../Helpers/Errors';
import { ExitCode } from '../../Helpers/ExitCode';
import type { AutomationOptions } from '../../Helpers/Options';
import { automationFlags } from '../../Helpers/Options';
import { formatOutput, resolveOutputMode } from '../../Helpers/Output';
import type { ConfigSource } from '../../Infrastructure/ActiveContext';
import { ActiveCliContext, ActiveContext } from '../../Infrastructure/ActiveContext';

const CONTEXT_METADATA = {
  name: 'context',
  summary: 'Print the active CLI context without secrets',
  description:
    'Print the active profile, config root, cache root, backend target, auth state, and config source summary without exposing secrets.',
  owner: '@pawrrtal/cli/Modules/Context',
  aliases: ['whoami'],
  flags: AUTOMATION_FLAG_METADATA,
  examples: [
    { command: 'paw context', description: 'Inspect the active context' },
    { command: 'paw context --json', description: 'Inspect the active context for automation' },
    { command: 'paw whoami --plain', description: 'Print the same context through the alias' },
  ],
  environment: [
    { name: 'PAW_HOME', purpose: 'Overrides config and cache roots' },
    { name: 'PAW_PROFILE', purpose: 'Selects the profile when --profile is absent' },
    { name: 'PAW_BACKEND_URL', purpose: 'Overrides the backend target' },
  ],
  notes: ['`paw whoami` is an alias for this command.', 'Secret-like config values are never printed.'],
  outputModes: ['human', 'json', 'plain'],
  structuredOutputs: [
    {
      mode: 'json',
      contract: 'ActiveContext',
      description: 'Schema-backed active profile, state roots, backend target, auth state, and config source summary.',
    },
  ],
  exitCodes: [ExitCode.success, ExitCode.usage, ExitCode.local],
} satisfies CommandMetadata;

/** Command module for inspecting the active CLI context. */
export const ContextCommand = {
  command: applyCommandMetadata(
    Command.make('context', automationFlags, handleContext).pipe(Command.withAlias('whoami')),
    CONTEXT_METADATA
  ),
  metadata: CONTEXT_METADATA,
} satisfies CommandModule<
  'context',
  AutomationOptions,
  EmptyCommandContext,
  UsageError | VerificationError,
  ActiveCliContext
>;

/** Prints the resolved active context. */
function handleContext(
  options: AutomationOptions
): Effect.Effect<void, UsageError | VerificationError, ActiveCliContext> {
  return Effect.gen(function* () {
    const mode = yield* resolveOutputMode(options);
    const context = yield* ActiveCliContext;
    const output = yield* formatOutput(context, mode, contextFormatters);
    yield* Console.log(output);
  });
}

const contextFormatters = {
  human: (context: ActiveContext): string =>
    [
      `Profile: ${context.profile}`,
      `Config Root: ${context.configRoot}`,
      `Cache Root: ${context.cacheRoot}`,
      `Backend Target: ${context.backendTarget ?? context.backendTargetUnsetReason}`,
      `Auth State: ${context.authState}`,
      'Sources:',
      ...context.configSources.map((source: ConfigSource) => `  ${source.key}: ${source.source}`),
    ].join('\n'),
  json: {
    schema: ActiveContext,
    render: (context: ActiveContext): ActiveContext => context,
  },
  plain: (context: ActiveContext): string =>
    [
      context.profile,
      context.configRoot,
      context.cacheRoot,
      context.backendTarget ?? '',
      context.authState,
      context.configSources.map((source: ConfigSource) => `${source.key}=${source.source}`).join(','),
    ].join('\t'),
};

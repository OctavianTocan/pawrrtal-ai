import { BunServices } from '@effect/platform-bun';
import type { FileSystem, Path } from 'effect';
import { Console, Effect, Layer } from 'effect';
import { Command } from 'effect/unstable/cli';
import type { RuntimeCommandRegistry } from './Commands';
import { DefaultCommandRegistry, validateCommandRegistry } from './Commands';
import { normalizeArgv } from './Helpers/Argv';
import type { CommandMetadata, ParameterMetadata } from './Helpers/CommandMetadata';
import type { CliProcess } from './Helpers/Config';
import { CliProcessLive, resolveActiveContext } from './Helpers/Config';
import type { PawCliError, UsageError } from './Helpers/Errors';
import { errorToExitCode, renderError, toCliError } from './Helpers/Errors';
import type { RootOptions } from './Helpers/Options';
import { rootSharedFlags } from './Helpers/Options';
import { ActiveCliContext } from './Modules/Context/Domain';

/** Current CLI package version printed by `paw --version`. */
export const VERSION = '0.1.0';

type PawRootCommand = Command.Command<
  'paw',
  never,
  RootOptions,
  PawCliError,
  CliProcess | FileSystem.FileSystem | Path.Path
>;

const RootCommand = Command.make('paw').pipe(
  Command.withSharedFlags(rootSharedFlags),
  Command.withDescription(
    'Operate Pawrrtal from a small, agent-friendly CLI. This first slice exposes local health, active context, shell completions, and stable output/config conventions.'
  ),
  Command.withExamples([
    { command: 'paw doctor', description: 'Check local CLI readiness' },
    { command: 'paw context --json', description: 'Print active context as JSON' },
    { command: 'paw completions zsh', description: 'Print zsh completions' },
  ])
);

/** Bun-backed layer required by the CLI entrypoint. */
export const MainLayer = Layer.mergeAll(BunServices.layer, CliProcessLive);

/**
 * Builds the root command from a registry.
 *
 * @param registry - Command registry to install under the root command.
 * @returns Effect CLI command ready to run with Bun platform services.
 */
export function makeCliCommand(
  registry: RuntimeCommandRegistry = DefaultCommandRegistry
): Effect.Effect<PawRootCommand, UsageError> {
  return validateCommandRegistry(registry).pipe(
    Effect.map((validRegistry) =>
      RootCommand.pipe(
        Command.withSubcommands(validRegistry.modules.map((module) => module.command)),
        Command.provideEffect(ActiveCliContext, (rootOptions) => resolveActiveContext({ rootOptions }))
      )
    )
  );
}

/**
 * Builds the runnable CLI effect for a process argument vector.
 *
 * @param args - Raw CLI arguments excluding the Bun executable and script path.
 * @returns Effect that prints command output or fails with a public exit code.
 */
export function makeCli(args: ReadonlyArray<string>): Effect.Effect<void, number, never> {
  return Effect.gen(function* () {
    const normalizedArgs = normalizeArgv(args);
    const wasHandled = yield* runPreparsedSurface({ args: normalizedArgs, registry: DefaultCommandRegistry });
    if (wasHandled) {
      return;
    }

    const command = yield* makeCliCommand();
    const run = Command.runWith(command, { version: VERSION });
    yield* run(normalizedArgs);
  }).pipe(
    Effect.provide(MainLayer),
    Effect.catchIf(() => true, translateCliError, translateCliError)
  );
}

/** Translates any CLI failure into stderr output and an exit code. */
function translateCliError(error: unknown): Effect.Effect<never, number> {
  return Effect.gen(function* () {
    const cliError = toCliError(error);
    yield* Console.error(renderError(cliError));
    return yield* Effect.fail(errorToExitCode(cliError));
  });
}

/** Handles help/version flags whose aliases differ from Effect built-ins. */
function runPreparsedSurface(input: {
  readonly args: ReadonlyArray<string>;
  readonly registry: RuntimeCommandRegistry;
}): Effect.Effect<boolean> {
  return Effect.gen(function* () {
    if (input.args.includes('--version')) {
      yield* Console.log(`paw v${VERSION}`);
      return true;
    }

    if (input.args.includes('--help') || input.args.includes('-h')) {
      yield* Console.log(formatHelp({ args: input.args, metadata: input.registry.rootMetadata }));
      return true;
    }

    return false;
  });
}

/** Formats root or command help from module metadata. */
function formatHelp(input: { readonly args: ReadonlyArray<string>; readonly metadata: CommandMetadata }): string {
  const commandName = selectedCommandName(input.args);
  const command = commandName
    ? input.metadata.subcommands?.find((candidate) => commandMatches(candidate, commandName))
    : undefined;

  return command ? formatCommandHelp(command) : formatRootHelp(input.metadata);
}

/** Formats root help. */
function formatRootHelp(metadata: CommandMetadata): string {
  return [
    'SUMMARY',
    `  ${metadata.summary}`,
    '',
    'DESCRIPTION',
    `  ${metadata.description}`,
    '',
    'USAGE',
    '  paw <command> [options]',
    '',
    'GLOBAL OPTIONS',
    '  -h, --help           Print help for the current command path',
    '  -V, --version        Print CLI version',
    '  -v, --verbose        Print expanded diagnostics and source chains',
    '  --profile string     Run this invocation against a specific profile',
    '  --backend-url string Run this invocation against a specific backend target',
    '',
    'COMMANDS',
    ...(metadata.subcommands ?? []).map(formatCommandListItem),
    '',
    formatEnvironment(metadata.environment ?? []),
    formatNotes(metadata.notes ?? []),
    formatExamples(metadata),
  ]
    .filter((line) => line.length > 0)
    .join('\n');
}

/** Formats help for one command. */
function formatCommandHelp(metadata: CommandMetadata): string {
  return [
    'SUMMARY',
    `  ${metadata.summary}`,
    '',
    'DESCRIPTION',
    `  ${metadata.description}`,
    '',
    'USAGE',
    `  paw ${metadata.name}${formatArgumentsUsage(metadata)} [options]`,
    '',
    formatArguments(metadata.arguments ?? []),
    formatOptions(metadata.flags ?? []),
    formatEnvironment(metadata.environment ?? []),
    formatNotes(metadata.notes ?? []),
    formatExamples(metadata),
  ]
    .filter((line) => line.length > 0)
    .join('\n');
}

/** Returns the first command token from an argv list. */
function selectedCommandName(args: ReadonlyArray<string>): string | undefined {
  return args.find((arg) => !arg.startsWith('-'));
}

/** Returns true when a command metadata entry matches a name or alias. */
function commandMatches(metadata: CommandMetadata, name: string): boolean {
  return metadata.name === name || (metadata.aliases ?? []).includes(name);
}

/** Formats one command list line. */
function formatCommandListItem(metadata: CommandMetadata): string {
  const aliases = metadata.aliases?.length ? `, ${metadata.aliases.join(', ')}` : '';
  return `  ${metadata.name}${aliases}  ${metadata.summary}`;
}

/** Formats positional usage. */
function formatArgumentsUsage(metadata: CommandMetadata): string {
  const args = metadata.arguments ?? [];
  if (args.length === 0) {
    return '';
  }
  return ` ${args.map((arg) => `<${arg.name}>`).join(' ')}`;
}

/** Formats positional argument details. */
function formatArguments(args: ReadonlyArray<ParameterMetadata>): string {
  if (args.length === 0) {
    return '';
  }
  return ['ARGUMENTS', ...args.map((arg) => `  ${arg.name}  ${arg.description}`), ''].join('\n');
}

/** Formats option details. */
function formatOptions(flags: ReadonlyArray<ParameterMetadata>): string {
  if (flags.length === 0) {
    return '';
  }
  return ['OPTIONS', ...flags.map(formatFlag), ''].join('\n');
}

/** Formats environment variables that affect a command. */
function formatEnvironment(environment: NonNullable<CommandMetadata['environment']>): string {
  if (environment.length === 0) {
    return '';
  }
  return ['ENVIRONMENT', ...environment.map((entry) => `  ${entry.name}  ${entry.purpose}`), ''].join('\n');
}

/** Formats command notes. */
function formatNotes(notes: ReadonlyArray<string>): string {
  if (notes.length === 0) {
    return '';
  }
  return ['NOTES', ...notes.map((note) => `  ${note}`), ''].join('\n');
}

/** Formats one option line. */
function formatFlag(flag: ParameterMetadata): string {
  const aliases = flag.aliases?.map((alias) => `-${alias}, `).join('') ?? '';
  return `  ${aliases}--${flag.name}  ${flag.description}`;
}

/** Formats command examples. */
function formatExamples(metadata: CommandMetadata): string {
  if (!metadata.examples?.length) {
    return '';
  }
  return ['EXAMPLES', ...metadata.examples.flatMap(formatExample)].join('\n');
}

/** Formats one command example. */
function formatExample(example: { readonly command: string; readonly description?: string }): ReadonlyArray<string> {
  return example.description ? [`  # ${example.description}`, `  ${example.command}`] : [`  ${example.command}`];
}

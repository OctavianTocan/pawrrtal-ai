import { BunServices } from '@effect/platform-bun';
import type { FileSystem, Path } from 'effect';
import { Cause, Console, Effect, Layer } from 'effect';
import { CliError, CliOutput, Command } from 'effect/unstable/cli';
import type { RuntimeCommandRegistry } from './Commands';
import { DefaultCommandRegistry, validateCommandRegistry } from './Commands';
import { normalizeArgv } from './Helpers/Argv';
import { applyCommandMetadata } from './Helpers/CommandMetadata';
import type { CliProcess } from './Helpers/Config';
import { CliProcessLive, resolveActiveContext } from './Helpers/Config';
import type { PawCliError, UsageError } from './Helpers/Errors';
import { errorToExitCode, failUsage, renderError, toCliError } from './Helpers/Errors';
import { ExitCode } from './Helpers/ExitCode';
import { formatCommandHelp, formatHelp } from './Helpers/Help';
import type { RootOptions } from './Helpers/Options';
import { rootSharedFlags } from './Helpers/Options';
import { CLI_VERSION } from './Helpers/Version';
import { ActiveCliContext } from './Infrastructure/ActiveContext';

type PawRootCommand = Command.Command<
  'paw',
  never,
  RootOptions,
  PawCliError,
  CliProcess | FileSystem.FileSystem | Path.Path
>;

/** Formatter used only for Effect parser failures; metadata owns normal help. */
const PawCliOutputLayer = CliOutput.layer({
  formatHelpDoc: (): string => '',
  formatCliError: (error): string => error.message,
  formatError: (error): string => `Error: ${error.message}`,
  formatVersion: (_name, version): string => `paw v${version}`,
  formatErrors: (): string => '',
});

/** Bun-backed layer required by the CLI entrypoint. */
export const MainLayer = Layer.mergeAll(BunServices.layer, CliProcessLive, PawCliOutputLayer);

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
      applyCommandMetadata(
        Command.make('paw').pipe(
          Command.withSharedFlags(rootSharedFlags),
          Command.withSubcommands(validRegistry.modules.map((module) => module.command)),
          Command.provideEffect(ActiveCliContext, (rootOptions) => resolveActiveContext({ rootOptions }))
        ),
        validRegistry.rootMetadata
      )
    )
  );
}

/**
 * Builds the runnable CLI effect for a process argument vector.
 *
 * @param args - Raw CLI arguments excluding the Bun executable and script path.
 * @returns Effect that prints output and sets the process exit code for handled failures.
 */
export function makeCli(args: ReadonlyArray<string>): Effect.Effect<void, never, never> {
  return Effect.gen(function* () {
    const normalizedArgs = normalizeArgv(args);
    const wasHandled = yield* runPreparsedSurface({ args: normalizedArgs, registry: DefaultCommandRegistry });
    if (wasHandled) {
      return;
    }

    const command = yield* makeCliCommand();
    const run = Command.runWith(command, { version: CLI_VERSION });
    yield* run(normalizedArgs);
  }).pipe(Effect.provide(MainLayer), catchAllCliFailures({ args: normalizeArgv(args) }));
}

/** Catches typed failures and defects through the public CLI renderer. */
function catchAllCliFailures(options: {
  readonly args: ReadonlyArray<string>;
}): <A, E, R>(self: Effect.Effect<A, E, R>) => Effect.Effect<A | void, never, R> {
  return Effect.catchCause((cause) =>
    translateCliError(Cause.squash(cause), { isVerbose: hasVerboseFlag(options.args) })
  );
}

/** Translates any CLI failure into stderr output and an exit code. */
function translateCliError(
  error: unknown,
  options: { readonly isVerbose: boolean }
): Effect.Effect<void, never, never> {
  if (CliError.isCliError(error) && error._tag === 'ShowHelp') {
    if (error.errors.length === 0) {
      return setExitCode(ExitCode.success);
    }

    return Effect.gen(function* () {
      yield* Console.error(renderError(toCliError(error), { isVerbose: options.isVerbose }));
      yield* setExitCode(ExitCode.usage);
    });
  }

  return Effect.gen(function* () {
    const cliError = toCliError(error);
    yield* Console.error(renderError(cliError, { isVerbose: options.isVerbose }));
    yield* setExitCode(errorToExitCode(cliError));
  });
}

/** Sets the process exit code without failing the Effect fiber. */
function setExitCode(code: number): Effect.Effect<void> {
  return Effect.sync(() => {
    process.exitCode = code;
  });
}

/** Handles help/version flags whose aliases differ from Effect built-ins. */
function runPreparsedSurface(input: {
  readonly args: ReadonlyArray<string>;
  readonly registry: RuntimeCommandRegistry;
}): Effect.Effect<boolean, UsageError> {
  return Effect.gen(function* () {
    if (input.args.length === 0) {
      yield* Console.log(formatHelp({ metadata: input.registry.rootMetadata }));
      return true;
    }

    if (input.args.length === 1 && input.args[0] === '--version') {
      yield* Console.log(`paw v${CLI_VERSION}`);
      return true;
    }

    if (input.args.includes('--version')) {
      return yield* failUsage('The version flag is only available at the root.', 'Run `paw --version`.');
    }

    if (input.args.some(isHelpFlag)) {
      const commandName = selectedCommandName(input.args);
      if (!commandName) {
        yield* Console.log(formatHelp({ metadata: input.registry.rootMetadata }));
        return true;
      }

      const command = input.registry.rootMetadata.subcommands?.find((candidate) =>
        commandMatches(candidate, commandName)
      );
      if (command) {
        yield* Console.log(formatCommandHelp(command));
        return true;
      }

      return yield* failUsage(`Unknown subcommand "${commandName}" for "paw".`);
    }

    return false;
  });
}

/** Returns the first command token from an argv list. */
function selectedCommandName(args: ReadonlyArray<string>): string | undefined {
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--profile' || arg === '--backend-url') {
      index += 1;
      continue;
    }
    if (arg && !arg.startsWith('-')) {
      return arg;
    }
  }
  return undefined;
}

/** Returns true when a command metadata entry matches a name or alias. */
function commandMatches(
  metadata: NonNullable<RuntimeCommandRegistry['rootMetadata']['subcommands']>[number],
  name: string
): boolean {
  return metadata.name === name || (metadata.aliases ?? []).includes(name);
}

/** Returns true when an argv token requests help. */
function isHelpFlag(arg: string | undefined): boolean {
  return arg === '--help' || arg === '-h';
}

/** Returns true when verbose diagnostics were requested. */
function hasVerboseFlag(args: ReadonlyArray<string>): boolean {
  return args.includes('--verbose');
}

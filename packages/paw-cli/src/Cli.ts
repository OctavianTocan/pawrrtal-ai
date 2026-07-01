import { BunServices } from '@effect/platform-bun';
import type { FileSystem, Path } from 'effect';
import { Cause, Console, Effect, Layer, Option, Result } from 'effect';
import { CliError, CliOutput, Command } from 'effect/unstable/cli';
import type { RuntimeCommandRegistry } from './Commands';
import { DefaultCommandRegistry, validateCommandRegistry } from './Commands';
import { normalizeArgv } from './Helpers/Argv';
import { applyCommandMetadata } from './Helpers/CommandMetadata';
import type { CliProcess } from './Helpers/Config';
import { CliProcessLive, resolveActiveContext } from './Helpers/Config';
import type { PawCliError } from './Helpers/Errors';
import {
  AuthError,
  ConfigError,
  ExternalError,
  errorToExitCode,
  failUsage,
  renderError,
  renderErrorEffect,
  toCliError,
  UnexpectedError,
  UsageError,
  VerificationError,
} from './Helpers/Errors';
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
          Command.provideEffect(ActiveCliContext, (rootOptions) =>
            resolveActiveContext({ rootOptions, cwd: Option.none() })
          )
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
    translateCliCause(cause, {
      isJson: hasJsonFlag(options.args),
      isVerbose: hasVerboseFlag(options.args),
    })
  );
}

/** Translates any CLI cause into stderr output and an exit code. */
function translateCliCause<E>(
  cause: Cause.Cause<E>,
  options: { readonly isJson: boolean; readonly isVerbose: boolean }
): Effect.Effect<void, never, never> {
  const cliError = causeToCliError(cause);
  if (CliError.isCliError(cliError) && cliError._tag === 'ShowHelp') {
    if (cliError.errors.length === 0) {
      return setExitCode(ExitCode.success);
    }

    return Effect.gen(function* () {
      yield* Console.error(renderError(toCliError(cliError), { isJson: options.isJson, isVerbose: options.isVerbose }));
      yield* setExitCode(ExitCode.usage);
    });
  }

  return Effect.gen(function* () {
    const pawError = addVerboseCauseDetails(toCliError(cliError), cause, options);
    const rendered = yield* renderErrorEffect(pawError, { isJson: options.isJson, isVerbose: options.isVerbose }).pipe(
      Effect.catchCause(() =>
        Effect.succeed(
          renderError(toCliError(new Error('CLI error payload did not match its public schema.')), {
            isJson: false,
            isVerbose: options.isVerbose,
          })
        )
      )
    );
    yield* Console.error(rendered);
    yield* setExitCode(errorToExitCode(pawError));
  });
}

/** Converts the first relevant cause reason into a public CLI error. */
function causeToCliError<E>(cause: Cause.Cause<E>): PawCliError | CliError.CliError {
  const failure = Cause.findErrorOption(cause);
  if (Option.isSome(failure)) {
    if (CliError.isCliError(failure.value)) {
      return failure.value;
    }
    return toCliError(failure.value);
  }

  const defect = Cause.findDefect(cause);
  if (Result.isSuccess(defect)) {
    return toCliError(defect.success);
  }

  return toCliError(new Error('CLI execution interrupted.'));
}

/** Adds full cause rendering to verbose errors when no richer detail exists. */
function addVerboseCauseDetails<E>(
  error: PawCliError,
  cause: Cause.Cause<E>,
  options: { readonly isVerbose: boolean }
): PawCliError {
  if (!options.isVerbose) {
    return error;
  }

  const causeDetails = Cause.pretty(cause);
  if (causeDetails.length === 0) {
    return error;
  }
  const existingDetails = 'details' in error && error.details !== null ? error.details : null;
  const details = existingDetails === null ? causeDetails : `${existingDetails}\n\n${causeDetails}`;
  const fields = makeVerboseErrorFields(error, details);

  switch (error._tag) {
    case 'UsageError':
      return new UsageError(fields);
    case 'ConfigError':
      return new ConfigError(fields);
    case 'AuthError':
      return new AuthError(fields);
    case 'ExternalError':
      return new ExternalError(fields);
    case 'VerificationError':
      return new VerificationError(fields);
    case 'UnexpectedError':
      return new UnexpectedError(fields);
    default:
      return assertNever(error);
  }
}

type VerboseErrorFields = {
  readonly message: string;
  readonly hint?: string | null;
  readonly details: string;
};

/** Builds constructor fields without materializing absent optional properties. */
function makeVerboseErrorFields(error: PawCliError, details: string): VerboseErrorFields {
  if ('hint' in error) {
    return { message: error.message, hint: error.hint, details };
  }

  return { message: error.message, details };
}

/** Fails when a tagged CLI error union grows without verbose support. */
function assertNever(error: never): never {
  throw new Error(`Unhandled CLI error: ${String(error)}`);
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
      return yield* Option.match(selectedCommandName(input.args), {
        onNone: () =>
          Effect.gen(function* () {
            yield* Console.log(formatHelp({ metadata: input.registry.rootMetadata }));
            return true;
          }),
        onSome: (commandName) =>
          Effect.gen(function* () {
            const command = Option.fromIterable(
              (input.registry.rootMetadata.subcommands ?? []).filter((candidate) =>
                commandMatches(candidate, commandName)
              )
            );
            if (Option.isSome(command)) {
              yield* Console.log(formatCommandHelp(command.value));
              return true;
            }

            return yield* failUsage(`Unknown subcommand "${commandName}" for "paw".`);
          }),
      });
    }

    return false;
  });
}

/** Returns the first command token from an argv list. */
function selectedCommandName(args: ReadonlyArray<string>): Option.Option<string> {
  let shouldSkipNext = false;
  for (const arg of args) {
    if (shouldSkipNext) {
      shouldSkipNext = false;
      continue;
    }
    if (arg === '--profile' || arg === '--backend-url') {
      shouldSkipNext = true;
      continue;
    }
    if (!arg.startsWith('-')) {
      return Option.some(arg);
    }
  }
  return Option.none();
}

/** Returns true when a command metadata entry matches a name or alias. */
function commandMatches(
  metadata: NonNullable<RuntimeCommandRegistry['rootMetadata']['subcommands']>[number],
  name: string
): boolean {
  return metadata.name === name || (metadata.aliases ?? []).includes(name);
}

/** Returns true when an argv token requests help. */
function isHelpFlag(arg: string): boolean {
  return arg === '--help' || arg === '-h';
}

/** Returns true when verbose diagnostics were requested. */
function hasVerboseFlag(args: ReadonlyArray<string>): boolean {
  return args.includes('--verbose');
}

/** Returns true when structured JSON was requested anywhere in argv. */
function hasJsonFlag(args: ReadonlyArray<string>): boolean {
  return args.includes('--json');
}

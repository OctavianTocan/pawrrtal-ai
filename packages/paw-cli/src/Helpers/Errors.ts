import { Data, Effect } from 'effect';
import { CliError } from 'effect/unstable/cli';
import { ExitCode } from './ExitCode';

export type CliErrorKind = 'usage' | 'config' | 'auth' | 'external' | 'verification' | 'unexpected';

export type ErrorRenderOptions = {
  readonly isJson?: boolean;
  readonly isVerbose?: boolean;
};

type CliErrorFields = {
  readonly message: string;
  readonly hint?: string;
  readonly details?: string;
};

type CliErrorFieldInput = {
  readonly message: string;
  readonly hint?: string | undefined;
  readonly details?: string | undefined;
};

/** Usage, validation, or ambiguous-input failure. */
export class UsageError extends Data.TaggedError('UsageError')<CliErrorFields> {}

/** Local filesystem or configuration failure. */
export class ConfigError extends Data.TaggedError('ConfigError')<CliErrorFields> {}

/** Authentication or active-context denial failure. */
export class AuthError extends Data.TaggedError('AuthError')<CliErrorFields> {}

/** Backend, network, external process, or dependency failure. */
export class ExternalError extends Data.TaggedError('ExternalError')<CliErrorFields> {}

/** Future assertion or verification failure. */
export class VerificationError extends Data.TaggedError('VerificationError')<CliErrorFields> {}

/** Unexpected runtime failure normalized for CLI rendering. */
export class UnexpectedError extends Data.TaggedError('UnexpectedError')<CliErrorFields> {}

export type PawCliError = UsageError | ConfigError | AuthError | ExternalError | VerificationError | UnexpectedError;

/**
 * Fails with a usage error.
 *
 * @param message - Human-readable validation failure.
 * @param hint - Optional recovery hint for stderr.
 * @param details - Optional verbose diagnostic detail.
 * @returns Effect that fails with `UsageError`.
 */
export function failUsage(message: string, hint?: string, details?: string): Effect.Effect<never, UsageError> {
  return Effect.fail(new UsageError(errorFields({ message, hint, details })));
}

/**
 * Fails with a local configuration error.
 *
 * @param message - Human-readable configuration failure.
 * @param hint - Optional recovery hint for stderr.
 * @returns Effect that fails with `ConfigError`.
 */
export function failConfig(message: string, hint?: string): Effect.Effect<never, ConfigError> {
  return Effect.fail(new ConfigError(errorFields({ message, hint })));
}

/**
 * Fails with an external dependency error.
 *
 * @param message - Human-readable dependency failure.
 * @param hint - Optional recovery hint for stderr.
 * @param details - Optional verbose diagnostic detail.
 * @returns Effect that fails with `ExternalError`.
 */
export function failExternal(message: string, hint?: string, details?: string): Effect.Effect<never, ExternalError> {
  return Effect.fail(new ExternalError(errorFields({ message, hint, details })));
}

/**
 * Converts an unknown value into a structured CLI error.
 *
 * @param error - Unknown failure value from Effect CLI or runtime code.
 * @returns Tagged Paw CLI error with a public category.
 */
export function toCliError(error: unknown): PawCliError {
  if (isPawCliError(error)) {
    return error;
  }

  if (CliError.isCliError(error)) {
    return cliParserErrorToPawError(error);
  }

  if (error instanceof Error) {
    return new UnexpectedError(errorFields({ message: error.message, details: error.stack }));
  }

  return new UnexpectedError({ message: String(error) });
}

/** Converts Effect CLI parser errors to Paw CLI errors. */
function cliParserErrorToPawError(error: CliError.CliError): PawCliError {
  if (error._tag === 'UserError') {
    return toCliError(error.cause);
  }

  if (error._tag === 'DuplicateOption') {
    return new ConfigError(errorFields({ message: error.message }));
  }

  if (error._tag === 'ShowHelp') {
    const message = error.errors[0]?.message ?? error.message;
    const details = error.errors.map((nestedError) => nestedError.message).join('\n');
    return new UsageError(errorFields({ message, details }));
  }

  return new UsageError(errorFields({ message: error.message }));
}

/**
 * Returns true when an unknown thrown value is a Paw CLI tagged error.
 *
 * @param error - Unknown value to narrow.
 * @returns Whether the value is a supported Paw CLI error.
 */
export function isPawCliError(error: unknown): error is PawCliError {
  return (
    error instanceof UsageError ||
    error instanceof ConfigError ||
    error instanceof AuthError ||
    error instanceof ExternalError ||
    error instanceof VerificationError ||
    error instanceof UnexpectedError
  );
}

/**
 * Returns the public error category for a CLI error.
 *
 * @param error - Tagged Paw CLI error.
 * @returns Stable error kind for human and JSON rendering.
 */
export function errorKind(error: PawCliError): CliErrorKind {
  switch (error._tag) {
    case 'UsageError':
      return 'usage';
    case 'ConfigError':
      return 'config';
    case 'AuthError':
      return 'auth';
    case 'ExternalError':
      return 'external';
    case 'VerificationError':
      return 'verification';
    case 'UnexpectedError':
      return 'unexpected';
    default:
      return assertNever(error);
  }
}

/**
 * Maps a CLI error to the public exit code contract.
 *
 * @param error - Tagged Paw CLI error.
 * @returns Public exit code for the error category.
 */
export function errorToExitCode(error: PawCliError): ExitCode {
  switch (error._tag) {
    case 'UsageError':
      return ExitCode.usage;
    case 'ConfigError':
    case 'UnexpectedError':
      return ExitCode.local;
    case 'AuthError':
      return ExitCode.auth;
    case 'ExternalError':
      return ExitCode.external;
    case 'VerificationError':
      return ExitCode.verification;
    default:
      return assertNever(error);
  }
}

/**
 * Renders an error for stderr.
 *
 * @param error - Tagged Paw CLI error to render.
 * @param options - Rendering options for JSON and verbose diagnostics.
 * @returns Text ready to write to stderr.
 */
export function renderError(error: PawCliError, options: ErrorRenderOptions = {}): string {
  if (options.isJson === true) {
    return JSON.stringify(
      {
        error: {
          kind: errorKind(error),
          message: error.message,
          hint: error.hint ?? null,
          details: options.isVerbose === true ? (error.details ?? null) : null,
        },
      },
      null,
      2
    );
  }

  const lines = [`Error: ${error.message}`];
  if (error.hint) {
    lines.push(`Hint: ${error.hint}`);
  }
  if (options.isVerbose === true && error.details) {
    lines.push(`Details: ${error.details}`);
  }
  return lines.join('\n');
}

/** Drops undefined optional fields before constructing tagged errors. */
function errorFields(input: CliErrorFieldInput): CliErrorFields {
  return {
    message: input.message,
    ...(input.hint ? { hint: input.hint } : {}),
    ...(input.details ? { details: input.details } : {}),
  };
}

/** Fails when a tagged CLI error union grows without renderer support. */
function assertNever(error: never): never {
  throw new Error(`Unhandled CLI error: ${String(error)}`);
}

import { Data, Effect } from 'effect';
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

export class UsageError extends Data.TaggedError('UsageError')<CliErrorFields> {}

export class ConfigError extends Data.TaggedError('ConfigError')<CliErrorFields> {}

export class AuthError extends Data.TaggedError('AuthError')<CliErrorFields> {}

export class ExternalError extends Data.TaggedError('ExternalError')<CliErrorFields> {}

export class VerificationError extends Data.TaggedError('VerificationError')<CliErrorFields> {}

export class UnexpectedError extends Data.TaggedError('UnexpectedError')<CliErrorFields> {}

export type PawCliError = UsageError | ConfigError | AuthError | ExternalError | VerificationError | UnexpectedError;

/** Fails with a usage error. */
export function failUsage(message: string, hint?: string): Effect.Effect<never, UsageError> {
  return Effect.fail(new UsageError(errorFields({ message, hint })));
}

/** Fails with a local configuration error. */
export function failConfig(message: string, hint?: string): Effect.Effect<never, ConfigError> {
  return Effect.fail(new ConfigError(errorFields({ message, hint })));
}

/** Fails with an external dependency error. */
export function failExternal(message: string, hint?: string, details?: string): Effect.Effect<never, ExternalError> {
  return Effect.fail(new ExternalError(errorFields({ message, hint, details })));
}

/** Converts an unknown value into a structured CLI error. */
export function toCliError(error: unknown): PawCliError {
  if (isPawCliError(error)) {
    return error;
  }

  if (error instanceof Error) {
    return new UnexpectedError(errorFields({ message: error.message, details: error.stack }));
  }

  return new UnexpectedError({ message: String(error) });
}

/** Returns true when an unknown thrown value is a Paw CLI tagged error. */
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

/** Returns the public error category for a CLI error. */
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
  }
}

/** Maps a CLI error to the public exit code contract. */
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
  }
}

/** Renders an error for stderr. */
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

import { Effect, Schema } from 'effect';
import { CliError } from 'effect/unstable/cli';
import { ExitCode } from './ExitCode';

export type CliErrorKind = 'usage' | 'config' | 'auth' | 'external' | 'verification' | 'unexpected';

export type ErrorRenderOptions = {
  readonly isJson: boolean;
  readonly isVerbose: boolean;
};

type CliErrorFields = {
  readonly message: string;
  readonly hint: string | null;
  readonly details: string | null;
};

const CliErrorFieldsSchema = {
  message: Schema.NonEmptyString,
  hint: Schema.NullOr(Schema.String).pipe(Schema.optionalKey, Schema.withConstructorDefault(Effect.succeed(null))),
  details: Schema.NullOr(Schema.String).pipe(Schema.optionalKey, Schema.withConstructorDefault(Effect.succeed(null))),
} as const;

const CliErrorKindSchema = Schema.Literals(['usage', 'config', 'auth', 'external', 'verification', 'unexpected']);

const DefaultErrorRenderOptions: ErrorRenderOptions = {
  isJson: false,
  isVerbose: false,
};

export class StructuredCliError extends Schema.Class<StructuredCliError>('StructuredCliError')(
  {
    kind: CliErrorKindSchema,
    message: Schema.NonEmptyString,
    hint: Schema.NullOr(Schema.String),
    details: Schema.NullOr(Schema.String),
  },
  {
    identifier: 'StructuredCliError',
    title: 'Structured CLI Error',
    description: 'Public structured error payload emitted by the Paw CLI.',
  }
) {}

export class StructuredCliErrorPayload extends Schema.Class<StructuredCliErrorPayload>('StructuredCliErrorPayload')(
  {
    error: StructuredCliError,
  },
  {
    identifier: 'StructuredCliErrorPayload',
    title: 'Structured CLI Error Payload',
    description: 'Envelope for JSON-formatted Paw CLI errors.',
  }
) {}

/** Usage, validation, or ambiguous-input failure. */
export class UsageError extends Schema.TaggedErrorClass<UsageError>()('UsageError', CliErrorFieldsSchema) {}

/** Local filesystem or configuration failure. */
export class ConfigError extends Schema.TaggedErrorClass<ConfigError>()('ConfigError', CliErrorFieldsSchema) {}

/** Authentication or active-context denial failure. */
export class AuthError extends Schema.TaggedErrorClass<AuthError>()('AuthError', CliErrorFieldsSchema) {}

/** Backend, network, external process, or dependency failure. */
export class ExternalError extends Schema.TaggedErrorClass<ExternalError>()('ExternalError', CliErrorFieldsSchema) {}

/** Future assertion or verification failure. */
export class VerificationError extends Schema.TaggedErrorClass<VerificationError>()(
  'VerificationError',
  CliErrorFieldsSchema
) {}

/** Unexpected runtime failure normalized for CLI rendering. */
export class UnexpectedError extends Schema.TaggedErrorClass<UnexpectedError>()(
  'UnexpectedError',
  CliErrorFieldsSchema
) {}

export type PawCliError = UsageError | ConfigError | AuthError | ExternalError | VerificationError | UnexpectedError;

/**
 * Fails with a usage error.
 *
 * @param message - Human-readable validation failure.
 * @param hint - Optional recovery hint for stderr.
 * @param details - Optional verbose diagnostic detail.
 * @returns Effect that fails with `UsageError`.
 */
export function failUsage(
  message: string,
  hint: string | null = null,
  details: string | null = null
): Effect.Effect<never, UsageError> {
  return Effect.fail(new UsageError(errorFields(message, hint, details)));
}

/**
 * Fails with a local configuration error.
 *
 * @param message - Human-readable configuration failure.
 * @param hint - Optional recovery hint for stderr.
 * @param details - Optional verbose diagnostic detail.
 * @returns Effect that fails with `ConfigError`.
 */
export function failConfig(
  message: string,
  hint: string | null = null,
  details: string | null = null
): Effect.Effect<never, ConfigError> {
  return Effect.fail(new ConfigError(errorFields(message, hint, details)));
}

/**
 * Fails with an external dependency error.
 *
 * @param message - Human-readable dependency failure.
 * @param hint - Optional recovery hint for stderr.
 * @param details - Optional verbose diagnostic detail.
 * @returns Effect that fails with `ExternalError`.
 */
export function failExternal(
  message: string,
  hint: string | null = null,
  details: string | null = null
): Effect.Effect<never, ExternalError> {
  return Effect.fail(new ExternalError(errorFields(message, hint, details)));
}

/**
 * Fails with a boundary verification error.
 *
 * @param message - Human-readable verification failure.
 * @param hint - Optional recovery hint for stderr.
 * @param details - Optional verbose diagnostic detail.
 * @returns Effect that fails with `VerificationError`.
 */
export function failVerification(
  message: string,
  hint: string | null = null,
  details: string | null = null
): Effect.Effect<never, VerificationError> {
  return Effect.fail(new VerificationError(errorFields(message, hint, details)));
}

/**
 * Converts a thrown value into a structured CLI error.
 *
 * @param error - Failure value from Effect CLI or runtime code.
 * @returns Tagged Paw CLI error with a public category.
 */
export function toCliError<E>(error: E): PawCliError {
  if (isPawCliError(error)) {
    return error;
  }

  if (CliError.isCliError(error)) {
    return cliParserErrorToPawError(error);
  }

  if (error instanceof Error) {
    return new UnexpectedError(errorFields(error.message, null, error.stack ?? null));
  }

  return new UnexpectedError({ message: String(error) });
}

/** Converts Effect CLI parser errors to Paw CLI errors. */
function cliParserErrorToPawError(error: CliError.CliError): PawCliError {
  if (error._tag === 'UserError') {
    return toCliError(error.cause);
  }

  if (error._tag === 'DuplicateOption') {
    return new ConfigError(errorFields(error.message));
  }

  if (error._tag === 'ShowHelp') {
    const message = error.errors[0]?.message ?? error.message;
    const details = error.errors.map((nestedError) => nestedError.message).join('\n');
    return new UsageError(errorFields(message, null, details));
  }

  return new UsageError(errorFields(error.message));
}

/**
 * Returns true when a thrown value is a Paw CLI tagged error.
 *
 * @param error - Value to narrow.
 * @returns Whether the value is a supported Paw CLI error.
 */
export function isPawCliError<E>(error: E): error is E & PawCliError {
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
export function renderError(error: PawCliError, options: ErrorRenderOptions = DefaultErrorRenderOptions): string {
  if (options.isJson === true) {
    return JSON.stringify(makeStructuredErrorPayload(error, options), null, 2);
  }

  const lines = [`Error: ${error.message}`];
  if (error.hint !== null) {
    lines.push(`Hint: ${error.hint}`);
  }
  if (options.isVerbose === true && error.details !== null) {
    lines.push(`Details: ${error.details}`);
  }
  return lines.join('\n');
}

/**
 * Renders an error through the schema-backed structured payload when JSON is requested.
 *
 * @param error - Tagged Paw CLI error to render.
 * @param options - Rendering options for JSON and verbose diagnostics.
 * @returns Text ready to write to stderr.
 */
export function renderErrorEffect(
  error: PawCliError,
  options: ErrorRenderOptions = DefaultErrorRenderOptions
): Effect.Effect<string, VerificationError> {
  if (options.isJson !== true) {
    return Effect.succeed(renderError(error, options));
  }

  return Schema.encodeEffect(StructuredCliErrorPayload)(makeStructuredErrorPayload(error, options)).pipe(
    Effect.map((encoded) => JSON.stringify(encoded, null, 2)),
    Effect.mapError(
      (schemaError) =>
        new VerificationError(
          errorFields('CLI error payload did not match its public schema.', null, String(schemaError))
        )
    )
  );
}

/**
 * Builds the public structured error payload.
 *
 * @param error - Tagged Paw CLI error.
 * @param options - Rendering options for verbose diagnostics.
 * @returns Schema-backed structured error payload.
 */
export function makeStructuredErrorPayload(
  error: PawCliError,
  options: ErrorRenderOptions = DefaultErrorRenderOptions
): StructuredCliErrorPayload {
  return new StructuredCliErrorPayload({
    error: new StructuredCliError({
      kind: errorKind(error),
      message: error.message,
      hint: error.hint ?? null,
      details: options.isVerbose === true ? (error.details ?? null) : null,
    }),
  });
}

/** Builds total tagged-error fields. */
function errorFields(message: string, hint: string | null = null, details: string | null = null): CliErrorFields {
  return { message, hint, details };
}

/** Fails when a tagged CLI error union grows without renderer support. */
function assertNever(error: never): never {
  throw new Error(`Unhandled CLI error: ${String(error)}`);
}

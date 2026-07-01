import { Effect, Schema } from 'effect';
import type { UsageError } from './Errors';
import { failUsage, VerificationError } from './Errors';

export type OutputMode = 'human' | 'json' | 'plain';

export type OutputModeOptions = {
  readonly json: boolean;
  readonly plain: boolean;
};

export type JsonFormatter<T, S extends Schema.Constraint> = {
  readonly schema: S;
  readonly render: (value: T) => S['Type'];
};

export type Formatters<T, S extends Schema.Constraint = Schema.Constraint> = {
  readonly human: (value: T) => string;
  readonly json?: JsonFormatter<T, S>;
  readonly plain?: (value: T) => string;
};

/**
 * Resolves automation flags to one output mode.
 *
 * @param options - Parsed `--json` and `--plain` flags.
 * @returns The selected output mode, or a usage error when modes conflict.
 */
export function resolveOutputMode(options: OutputModeOptions): Effect.Effect<OutputMode, UsageError> {
  if (options.json && options.plain) {
    return failUsage('Choose only one output mode.', 'Use either --json or --plain, not both.');
  }

  if (options.json) {
    return Effect.succeed('json');
  }

  if (options.plain) {
    return Effect.succeed('plain');
  }

  return Effect.succeed('human');
}

/**
 * Formats a command value for stdout.
 *
 * @param value - Command result to render.
 * @param mode - Output mode selected for this invocation.
 * @param formatters - Renderers for human, JSON, and plain output.
 * @returns Text ready to write to stdout.
 */
export function formatOutput<T, S extends Schema.Constraint>(
  value: T,
  mode: OutputMode,
  formatters: Formatters<T, S>
): Effect.Effect<string, VerificationError, S['EncodingServices']> {
  switch (mode) {
    case 'human':
      return Effect.succeed(formatters.human(value));
    case 'json':
      return formatJsonOutput(value, formatters);
    case 'plain':
      return Effect.succeed(formatters.plain ? formatters.plain(value) : formatters.human(value));
    default:
      return assertNever(mode);
  }
}

/** Encodes a command value through its declared JSON output schema. */
function formatJsonOutput<T, S extends Schema.Constraint>(
  value: T,
  formatters: Formatters<T, S>
): Effect.Effect<string, VerificationError, S['EncodingServices']> {
  if (!formatters.json) {
    return Effect.fail(
      new VerificationError({
        message: 'Command selected JSON output without a JSON formatter.',
        hint: 'Declare a JSON formatter with a schema for commands that expose --json.',
      })
    );
  }

  return Schema.encodeEffect(formatters.json.schema)(formatters.json.render(value)).pipe(
    Effect.map((encoded) => JSON.stringify(encoded, null, 2)),
    Effect.mapError(
      (schemaError) =>
        new VerificationError({
          message: 'Command output did not match its declared JSON schema.',
          details: String(schemaError),
        })
    )
  );
}

/** Fails when an output mode is added without a formatter branch. */
function assertNever(mode: never): never {
  throw new Error(`Unhandled output mode: ${String(mode)}`);
}

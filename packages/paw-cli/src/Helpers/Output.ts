import { Effect } from 'effect';
import type { UsageError } from './Errors';
import { failUsage } from './Errors';

export type OutputMode = 'human' | 'json' | 'plain';

export type OutputModeOptions = {
  readonly json: boolean;
  readonly plain: boolean;
};

export type Formatters<T> = {
  readonly human: (value: T) => string;
  readonly json?: (value: T) => unknown;
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
export function formatOutput<T>(value: T, mode: OutputMode, formatters: Formatters<T>): string {
  switch (mode) {
    case 'human':
      return formatters.human(value);
    case 'json':
      return JSON.stringify(formatters.json ? formatters.json(value) : value, null, 2);
    case 'plain':
      return formatters.plain ? formatters.plain(value) : formatters.human(value);
    default:
      return assertNever(mode);
  }
}

/** Fails when an output mode is added without a formatter branch. */
function assertNever(mode: never): never {
  throw new Error(`Unhandled output mode: ${String(mode)}`);
}

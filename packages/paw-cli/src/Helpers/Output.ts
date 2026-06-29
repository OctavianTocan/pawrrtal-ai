import { Effect } from 'effect';
import { failUsage, type UsageError } from './Errors';

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

/** Resolves automation flags to one output mode. */
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

/** Formats a command value for stdout. */
export function formatOutput<T>(value: T, mode: OutputMode, formatters: Formatters<T>): string {
  switch (mode) {
    case 'human':
      return formatters.human(value);
    case 'json':
      return JSON.stringify(formatters.json ? formatters.json(value) : value, null, 2);
    case 'plain':
      return formatters.plain ? formatters.plain(value) : formatters.human(value);
  }
}

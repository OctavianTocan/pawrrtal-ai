import { Effect } from 'effect';
import type { UsageError } from './Errors';
import { failUsage } from './Errors';

export type BodySourceKind = 'inline' | 'file' | 'stdin' | 'editor';

export type BodySourceOptions = {
  readonly inline?: string;
  readonly file?: string;
  readonly stdin?: string;
  readonly isEditorRequested?: boolean;
  readonly isInteractive?: boolean;
};

export type BodySource = {
  readonly kind: BodySourceKind;
  readonly value: string | null;
};

export type BodySourceResolution =
  | { readonly _tag: 'None' }
  | { readonly _tag: 'Selected'; readonly source: BodySource };

/**
 * Resolves mutually exclusive body/document input sources.
 *
 * @param options - Candidate body sources from flags, stdin, and terminal state.
 * @returns The selected body source, or `None` when no source was supplied.
 */
export function resolveBodySource(options: BodySourceOptions): Effect.Effect<BodySourceResolution, UsageError> {
  const sources = selectedSources(options);
  if (sources.length > 1) {
    return failUsage(
      'Only one body source may be supplied.',
      'Use one of --content, --file, stdin (-), or an interactive editor fallback.'
    );
  }

  const source = sources[0];
  if (!source) {
    return Effect.succeed({ _tag: 'None' as const });
  }

  if (source.kind === 'editor' && options.isInteractive !== true) {
    return failUsage(
      'Editor fallback requires an interactive terminal.',
      'Use --content, --file, or stdin for non-interactive calls.'
    );
  }

  return Effect.succeed({ _tag: 'Selected' as const, source });
}

/** Selects the input sources explicitly requested by the caller. */
function selectedSources(options: BodySourceOptions): ReadonlyArray<BodySource> {
  const sources: BodySource[] = [];
  if (hasText(options.inline)) {
    sources.push({ kind: 'inline', value: options.inline ?? '' });
  }
  if (hasText(options.file)) {
    sources.push({ kind: options.file === '-' ? 'stdin' : 'file', value: options.file ?? '' });
  }
  if (hasText(options.stdin)) {
    sources.push({ kind: 'stdin', value: options.stdin ?? '' });
  }
  if (options.isEditorRequested === true) {
    sources.push({ kind: 'editor', value: null });
  }
  return sources;
}

/** Returns true when a CLI-provided text value is intentionally present. */
function hasText(value: string | undefined): boolean {
  return value !== undefined && value.length > 0;
}

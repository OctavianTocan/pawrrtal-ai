/**
 * The read-path client (client B).
 *
 * Subscribes to the `conversations` shape via `@electric-sql/client` and
 * materializes a live `Map<id, row>`. This is the half files-first could never
 * do: a second client sees Postgres rows appear/update live, pushed by Electric
 * over the shape log — no polling, no manual refresh.
 */
import { type ChangeMessage, isChangeMessage, type Row, ShapeStream } from '@electric-sql/client';
import { ELECTRIC_URL } from './config.ts';

export interface ConversationRow extends Row {
  id: string;
  owner: string;
  title: string;
  last_message: string;
  turn_count: number;
  updated_at: string;
}

export interface ConversationShape {
  /** Live materialized rows keyed by primary key. */
  readonly rows: Map<string, ConversationRow>;
  /** Resolve once `predicate` holds, else reject after `timeoutMs`. */
  waitFor(predicate: (rows: Map<string, ConversationRow>) => boolean, timeoutMs: number): Promise<void>;
  /** Stop the stream. */
  close(): void;
}

export interface ShapeOptions {
  /** Scope the shape (e.g. `owner = 'alice'`). Ignored when going via the gatekeeper. */
  where?: string;
  /** Shape endpoint; defaults to Electric directly. Point at the proxy for M4. */
  url?: string;
  /** Extra request headers (e.g. the identity the proxy authenticates on). */
  headers?: Record<string, string>;
}

/**
 * Open a live subscription to the `conversations` shape. By default it hits
 * Electric directly (M3); pass `url`/`headers` to route through the gatekeeper
 * proxy (M4), which enforces the owner scope server-side regardless of `where`.
 */
export function openConversationShape(opts: ShapeOptions = {}): ConversationShape {
  const controller = new AbortController();
  const rows = new Map<string, ConversationRow>();
  const listeners = new Set<() => void>();

  const stream = new ShapeStream<ConversationRow>({
    url: opts.url ?? `${ELECTRIC_URL}/v1/shape`,
    params: { table: 'conversations', ...(opts.where ? { where: opts.where } : {}) },
    ...(opts.headers ? { headers: opts.headers } : {}),
    signal: controller.signal,
    // Tolerate the startup race where the shape is requested before Electric has
    // finished publishing the table; returning {} retries with the same params.
    onError: (error) => {
      process.stderr.write(`[shape] stream error (retrying): ${String(error)}\n`);
      return {};
    },
  });

  stream.subscribe((messages) => {
    let changed = false;
    for (const message of messages) {
      if (!isChangeMessage(message)) {
        continue;
      }
      changed = true;
      applyChange(rows, message);
    }
    if (changed) {
      for (const listener of listeners) {
        listener();
      }
    }
  });

  const waitFor = (predicate: (rows: Map<string, ConversationRow>) => boolean, timeoutMs: number): Promise<void> =>
    new Promise((resolve, reject) => {
      const check = (): boolean => {
        if (predicate(rows)) {
          cleanup();
          resolve();
          return true;
        }
        return false;
      };
      const timer = setTimeout(() => {
        cleanup();
        reject(new Error(`shape predicate not satisfied within ${timeoutMs}ms`));
      }, timeoutMs);
      const cleanup = (): void => {
        clearTimeout(timer);
        listeners.delete(check);
      };
      if (check()) {
        return;
      }
      listeners.add(check);
    });

  return {
    rows,
    waitFor,
    close: () => controller.abort(),
  };
}

/**
 * Fold one change message into the materialized row map.
 *
 * Keyed by the row's own `id` (the PK, always present in the change value),
 * NOT by Electric's structured `message.key` (e.g. `"public"."conversations"/"x"`)
 * — so callers can look up by the id they wrote. With the default replica an
 * update carries the PK plus only the changed columns, hence the merge.
 */
function applyChange(rows: Map<string, ConversationRow>, message: ChangeMessage<ConversationRow>): void {
  const id = String(message.value.id);
  if (message.headers.operation === 'delete') {
    rows.delete(id);
    return;
  }
  const existing = rows.get(id);
  rows.set(id, { ...(existing ?? {}), ...message.value } as ConversationRow);
}

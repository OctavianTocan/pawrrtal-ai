'use client';

import type { Dispatch, SetStateAction } from 'react';
import { useCallback, useDebugValue, useEffect, useRef, useSyncExternalStore } from 'react';

/**
 * Options for {@link usePersistedState}.
 */
export interface UsePersistedStateOptions<T> {
  /** localStorage key under which the value is persisted. */
  storageKey: string;
  /** Default value used when nothing is persisted (or persistence/validation fails). */
  defaultValue: T;
  /**
   * Optional runtime validator for the value parsed from storage.
   *
   * Returns `true` if the parsed value is a valid `T`. When omitted, any successfully
   * parsed JSON value is accepted, which is fine for primitives but unsafe for typed
   * unions — pass a guard whenever the on-disk shape might drift (renamed enum members,
   * stale users, manual edits in DevTools).
   */
  validate?: (value: unknown) => value is T;
}

/**
 * `useState` backed by `window.localStorage`, hydration-safe by construction.
 *
 * Built on `useSyncExternalStore`: the `getServerSnapshot` callback returns
 * `defaultValue`, so SSR and the first client render always emit identical
 * markup. The real persisted value is read on the second client render via
 * `getSnapshot`, after React has finished hydrating. This avoids the
 * SSR-vs-CSR mismatch that a synchronous `useState` initializer reading
 * `localStorage` would create.
 *
 * Cross-tab sync comes for free: the subscriber listens for `storage` events
 * and a custom in-page event, so changes from other tabs and from another
 * caller in this same tab both trigger a re-render in every consumer.
 *
 * Storage I/O is wrapped in try/catch because reads can throw in private
 * browsing or when storage access is blocked, and writes can throw on quota
 * exhaustion. When a `validate` guard is provided, persisted values that fail
 * validation are silently discarded in favour of `defaultValue` — protects
 * against renamed enum members still living in older users' storage.
 */
export function usePersistedState<T>(options: UsePersistedStateOptions<T>): [T, Dispatch<SetStateAction<T>>] {
  const { storageKey, defaultValue, validate } = options;

  // Refs decouple the latest defaultValue/validate from the memoized
  // `getSnapshot`/`subscribe` identities — the snapshot fns must stay stable
  // across renders or `useSyncExternalStore` will throw a "snapshot is not
  // cached" warning under StrictMode.
  const defaultValueRef = useRef(defaultValue);
  defaultValueRef.current = defaultValue;
  const validateRef = useRef(validate);
  validateRef.current = validate;

  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === 'undefined') {
        // SSR has no window to listen on — nothing to unsubscribe.
        return noop;
      }

      const handleStorage = (event: StorageEvent): void => {
        // Filter to our key — the storage event fires on every key in the document.
        if (event.storageArea === window.localStorage && event.key === storageKey) {
          onChange();
        }
      };
      const handleLocal = (event: Event): void => {
        if ((event as CustomEvent<string>).detail === storageKey) onChange();
      };

      window.addEventListener('storage', handleStorage);
      window.addEventListener(LOCAL_STORAGE_EVENT, handleLocal);
      return () => {
        window.removeEventListener('storage', handleStorage);
        window.removeEventListener(LOCAL_STORAGE_EVENT, handleLocal);
      };
    },
    [storageKey]
  );

  // `getSnapshot` is invariant for a given `storageKey` — the cache slot
  // inside `useSyncExternalStore` keys on its identity, so memoising it
  // stabilises the returned tuple.
  const getSnapshot = useCallback((): T => {
    return readPersistedValue(storageKey, defaultValueRef.current, validateRef.current);
  }, [storageKey]);

  // `getServerSnapshot` MUST return the same value on every call during the
  // initial client render — return defaultValue so SSR and the first client
  // commit produce identical HTML. The persisted value lands on the next
  // commit, after React calls `subscribe` and `getSnapshot` for real.
  const getServerSnapshot = useCallback((): T => defaultValueRef.current, []);

  const value = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  useDebugValue(value);

  const setValue = useCallback<Dispatch<SetStateAction<T>>>(
    (updater) => {
      if (typeof window === 'undefined') return;
      const next = typeof updater === 'function' ? (updater as (prev: T) => T)(getSnapshot()) : updater;
      writePersistedValue(storageKey, next);
      // Notify same-tab listeners — `storage` events only fire across tabs.
      window.dispatchEvent(new CustomEvent(LOCAL_STORAGE_EVENT, { detail: storageKey }));
    },
    [getSnapshot, storageKey]
  );

  // Backfill: if the user has nothing persisted yet, write the default once
  // after mount so the next page-load reads it back instead of bouncing
  // through `defaultValue` on every refresh. Wrapped in a guard so we don't
  // overwrite a value that's already there.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      if (window.localStorage.getItem(storageKey) === null) {
        writePersistedValue(storageKey, defaultValueRef.current);
      }
    } catch {
      // Private browsing or quota exhausted — silent.
    }
  }, [storageKey]);

  return [value, setValue];
}

/** Custom event name fired on the window so same-tab callers can subscribe. */
const LOCAL_STORAGE_EVENT = 'persisted-state:change';

/** Stable no-op returned in SSR/unsubscribe slots — avoids a fresh closure per call. */
function noop(): void {
  // intentionally empty — see callers
}

/**
 * Per-key cache of `{ raw: lastSeenString, value: parsed }`. `useSyncExternalStore`
 * calls `getSnapshot` multiple times per render and warns about an infinite loop
 * if it returns a different reference each time. For object/array values that's
 * exactly what `JSON.parse` does — fresh reference, identical contents — so we
 * key the cache on the raw localStorage string and only re-parse when it changes.
 *
 * Module-level so two consumers of the same key share a parsed reference. The
 * cache is bounded by the number of distinct storage keys ever seen (in practice
 * a small fixed set) and never holds onto stale entries beyond a re-write since
 * the next read with a different `raw` overwrites the slot.
 */
const snapshotCache = new Map<string, { raw: string | null; value: unknown }>();

/**
 * Read and validate a value from `localStorage`, falling back to `defaultValue`
 * when the entry is missing, unparseable, or fails the optional `validate` guard.
 *
 * Caches the parsed value by raw string (see {@link snapshotCache}) so repeated
 * reads with an unchanged underlying string return a stable reference — required
 * for `useSyncExternalStore` correctness when the value is an object or array.
 */

/**
 * Silently remove a localStorage key, swallowing quota / private-browsing
 * errors so the caller doesn't need a nested try-catch.
 */
function silentlyRemove(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* quota / private browsing — ignore */
  }
}

function readPersistedValue<T>(storageKey: string, defaultValue: T, validate?: (value: unknown) => value is T): T {
  if (typeof window === 'undefined') {
    return defaultValue;
  }

  let rawValue: string | null;
  try {
    rawValue = window.localStorage.getItem(storageKey);
  } catch {
    // Private browsing or storage access denied — fall back without caching
    // so a future call retries the read once the constraint clears.
    return defaultValue;
  }

  const cached = snapshotCache.get(storageKey);
  if (cached && cached.raw === rawValue) {
    // Re-validate against the *current* call's validator: the cache may have
    // been populated by a different caller passing a wider/no validator.
    if (validate && !validate(cached.value)) {
      return defaultValue;
    }
    return cached.value as T;
  }

  let parsed: T;
  if (rawValue === null) {
    parsed = defaultValue;
  } else {
    try {
      const parsedUnknown: unknown = JSON.parse(rawValue);
      if (validate && !validate(parsedUnknown)) {
        // Value is stale (e.g. renamed model ID). Remove it so the
        // default is written on next persist rather than staying
        // as an invisible bad value in storage indefinitely.
        silentlyRemove(storageKey);
        parsed = defaultValue;
      } else {
        parsed = parsedUnknown as T;
      }
    } catch {
      parsed = defaultValue;
    }
  }

  snapshotCache.set(storageKey, { raw: rawValue, value: parsed });
  return parsed;
}

/** Persist a value to localStorage, swallowing quota / availability errors. */
function writePersistedValue<T>(storageKey: string, value: T): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(value));
  } catch {
    // Storage write failed (quota exceeded, private browsing, etc.) — ignore.
  }
}

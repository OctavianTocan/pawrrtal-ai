import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { usePersistedState } from './use-persisted-state';

const KEY = 'use-persisted-state-test';

function clearKey(): void {
  try {
    (window.localStorage as Storage).removeItem(KEY);
  } catch {
    /* ignore */
  }
}

describe('usePersistedState', () => {
  beforeEach(clearKey);
  afterEach(clearKey);

  it('returns the default value when storage is empty', () => {
    const { result } = renderHook(() => usePersistedState({ storageKey: KEY, defaultValue: 'fallback' }));
    expect(result.current[0]).toBe('fallback');
  });

  it('persists values across re-renders', () => {
    const { result } = renderHook(() => usePersistedState({ storageKey: KEY, defaultValue: 0 }));
    act(() => {
      result.current[1](42);
    });
    expect(result.current[0]).toBe(42);
  });

  it('honors functional updaters', () => {
    const { result } = renderHook(() => usePersistedState({ storageKey: KEY, defaultValue: 1 }));
    act(() => {
      result.current[1]((prev) => prev + 10);
    });
    expect(result.current[0]).toBe(11);
  });

  it('discards values that fail the optional validator', () => {
    (window.localStorage as Storage).setItem(KEY, JSON.stringify('garbage'));
    const isNumber = (v: unknown): v is number => typeof v === 'number';
    const { result } = renderHook(() => usePersistedState({ storageKey: KEY, defaultValue: 7, validate: isNumber }));
    expect(result.current[0]).toBe(7);
  });
});

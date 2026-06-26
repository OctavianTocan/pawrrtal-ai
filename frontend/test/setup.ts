import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom doesn't ship a ResizeObserver — radix-ui's Slider, DropdownMenu,
// and a few other primitives crash without it. Stub the minimum surface
// so component tests render.
class ResizeObserverPolyfill {
  observe(): void {
    /* noop */
  }
  unobserve(): void {
    /* noop */
  }
  disconnect(): void {
    /* noop */
  }
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverPolyfill }).ResizeObserver = ResizeObserverPolyfill;
}

// jsdom under Bun's vitest can expose `window.localStorage` through Node's
// warning-emitting Web Storage getter when no localstorage file is configured.
// Install a deterministic in-memory Storage polyfill without touching the
// getter first so persistence-backed hooks have a quiet, working API in tests.
if (typeof window !== 'undefined') {
  const store = new Map<string, string>();
  const polyfill: Storage = {
    get length(): number {
      return store.size;
    },
    clear: (): void => {
      store.clear();
    },
    getItem: (key: string): string | null => (store.has(key) ? (store.get(key) as string) : null),
    setItem: (key: string, value: string): void => {
      store.set(key, String(value));
    },
    removeItem: (key: string): void => {
      store.delete(key);
    },
    key: (index: number): string | null => Array.from(store.keys())[index] ?? null,
  };
  Object.defineProperty(window, 'localStorage', {
    value: polyfill,
    configurable: true,
    writable: false,
  });
}

// jsdom's `Element.scrollIntoView` is undefined; radix-ui's submenu
// keyboard navigation calls it. Stub as a no-op so menu interactions
// don't crash the test runner.
// Guard for non-browser environments (e.g. Node-environment tests).
if (typeof Element !== 'undefined' && typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = (): void => {
    /* noop */
  };
}

// `window.matchMedia` isn't implemented in jsdom — `useIsMobile` and
// other responsive hooks call it during render. Provide a stub that
// always reports "not matching" plus the addEventListener noop.
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  (window as unknown as { matchMedia: (query: string) => MediaQueryList }).matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {
        /* legacy noop */
      },
      removeListener: () => {
        /* legacy noop */
      },
      addEventListener: () => {
        /* noop */
      },
      removeEventListener: () => {
        /* noop */
      },
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

afterEach((): void => {
  cleanup();
  // Clear the in-memory localStorage polyfill so persisted state from one
  // test (selected model, sidebar collapse, plan-mode flags, etc.) doesn't
  // leak into the next. Without this, a test's breadcrumb becomes another
  // test's mysterious goblin — passing in isolation, failing in the suite.
  if (typeof window !== 'undefined') {
    window.localStorage.clear();
  }
});

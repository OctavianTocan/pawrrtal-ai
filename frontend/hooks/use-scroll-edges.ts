/**
 * @file use-scroll-edges.ts
 * @brief Track whether a scrollable element has more content above/below the
 * currently visible region, so callers can show/hide top/bottom fade-mask
 * affordances.
 */

'use client';

import type { RefObject } from 'react';
import { useEffect, useState } from 'react';

/**
 * @brief Whether the scrollable element has content above and/or below the
 * visible area.
 */
export interface ScrollEdges {
  /** True when scrollTop > 0 — content exists above the visible area. */
  canScrollUp: boolean;
  /** True when scrollTop + clientHeight < scrollHeight — content exists below. */
  canScrollDown: boolean;
}

/**
 * @brief Watches a scrollable element and reports whether it has content
 * outside the visible window in each direction.
 *
 * Updates on `scroll` and `resize` (via `ResizeObserver`). Re-checks when the
 * ref's `.current` becomes available, which matters for forwarded refs that
 * resolve after the consumer mounts.
 *
 * Use to drive top/bottom fade-mask visibility — the typical pattern is:
 *
 * ```tsx
 * const ref = useRef<HTMLTextAreaElement>(null);
 * const { canScrollUp, canScrollDown } = useScrollEdges(ref);
 * return (
 *   <textarea
 *     ref={ref}
 *     data-scroll-up={canScrollUp}
 *     data-scroll-down={canScrollDown}
 *     // CSS uses [data-scroll-up='true'] / [data-scroll-down='true']
 *   />
 * );
 * ```
 *
 * @param ref Ref to the scrollable element
 * @returns Current scroll-edge state
 */
export function useScrollEdges<T extends HTMLElement>(ref: RefObject<T | null>): ScrollEdges {
  const [edges, setEdges] = useState<ScrollEdges>({
    canScrollUp: false,
    canScrollDown: false,
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = (): void => {
      // `scrollHeight - clientHeight - scrollTop` is the remaining scroll
      // distance below; a 1 px fudge avoids flicker at the rounding edge
      // where browsers report fractional values.
      const canScrollUp = el.scrollTop > 1;
      const canScrollDown = el.scrollHeight - el.clientHeight - el.scrollTop > 1;
      setEdges((prev) =>
        prev.canScrollUp === canScrollUp && prev.canScrollDown === canScrollDown ? prev : { canScrollUp, canScrollDown }
      );
    };

    update();
    el.addEventListener('scroll', update, { passive: true });
    // Watch for size changes so we re-check when the user types (textarea
    // auto-grows) or the container resizes around it.
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    observer?.observe(el);

    return () => {
      el.removeEventListener('scroll', update);
      observer?.disconnect();
    };
  }, [ref]);

  return edges;
}

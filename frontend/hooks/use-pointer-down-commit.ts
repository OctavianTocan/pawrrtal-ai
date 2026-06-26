'use client';

import type * as React from 'react';
import { useCallback, useRef } from 'react';

/** Event handlers for committing a selectable row before dropdown close timing can unmount it. */
export interface PointerDownCommitHandlers<T extends HTMLElement> {
  onClick: () => void;
  onPointerDown: (event: React.PointerEvent<T>) => void;
}

/**
 * Commits a dropdown selection on primary pointer-down, while keeping click as
 * the keyboard/fallback path and guarding against duplicate pointer + click
 * commits from the same interaction.
 */
export function usePointerDownCommit<T extends HTMLElement>(commit: () => void): PointerDownCommitHandlers<T> {
  const pointerCommittedRef = useRef(false);
  const onPointerDown = useCallback(
    (event: React.PointerEvent<T>): void => {
      if (event.button !== 0) return;
      event.preventDefault();
      pointerCommittedRef.current = true;
      commit();
    },
    [commit]
  );
  const onClick = useCallback((): void => {
    if (pointerCommittedRef.current) {
      pointerCommittedRef.current = false;
      return;
    }
    commit();
  }, [commit]);

  return { onClick, onPointerDown };
}

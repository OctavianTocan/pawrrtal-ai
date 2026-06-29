/**
 * Header row for the assistant's chain-of-thought panel.
 *
 * Animated gradient text running accent → info while the model streams,
 * three-dot animated tail, and a chevron that rotates 90° when the panel
 * expands.
 *
 * Visual decisions intentionally driven by design tokens (see
 * `globals.css`): `--thinking-gradient-from`, `--thinking-gradient-to`,
 * `--color-muted-foreground`, `--color-foreground`. No arbitrary colors.
 *
 * @fileoverview Chat — `ThinkingHeader`.
 */

'use client';

import { ChevronRightIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { formatThinkingDuration } from '../thinking-parser';

/**
 * Tick interval for the trailing dot animation.
 */
const DOTS_INTERVAL_MS = 500;

/**
 * Cycles `''`, `'.'`, `'..'`, `'...'` while not paused. Renders inside a
 * fixed-width span so the chevron position never jumps.
 */
function AnimatedDots({ paused }: { paused: boolean }): ReactNode {
  const [dots, setDots] = useState('');

  useEffect(() => {
    if (paused) return;
    const id = window.setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : `${prev}.`));
    }, DOTS_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [paused]);

  return (
    <span aria-hidden="true" className="inline-block w-[1em] text-left">
      {dots}
    </span>
  );
}

/**
 * Props for {@link ThinkingHeader}.
 */
export interface ThinkingHeaderProps {
  /** Whether the panel is currently expanded. Drives chevron rotation. */
  isOpen: boolean;
  /** Whether the model is still streaming this turn. Drives the gradient + dots. */
  isStreaming: boolean;
  /** Total reasoning duration in seconds, set once streaming finishes. */
  durationSeconds: number | undefined;
  /** Whether the panel has any expandable content (hides chevron when false). */
  hasExpandableContent: boolean;
  /** Toggle handler for the trigger button. */
  onToggle: () => void;
}

/**
 * Renders the trigger row for the chain-of-thought panel.
 *
 * @param props - Streaming/duration state and toggle handler.
 * @returns A button (when expandable) or static span otherwise.
 */
export function ThinkingHeader({
  isOpen,
  isStreaming,
  durationSeconds,
  hasExpandableContent,
  onToggle,
}: ThinkingHeaderProps): ReactNode {
  const label = isStreaming
    ? 'Thinking'
    : durationSeconds === undefined
      ? 'Thought'
      : formatThinkingDuration(durationSeconds);

  const textClass = cn('font-medium text-sm', isStreaming ? 'thinking-gradient-text' : 'text-muted-foreground');

  if (!hasExpandableContent) {
    return (
      <span className="inline-flex items-center gap-1">
        <span className={textClass}>{label}</span>
        {isStreaming ? <AnimatedDots paused={false} /> : null}
      </span>
    );
  }

  return (
    <button
      aria-expanded={isOpen}
      aria-label={isOpen ? 'Collapse thinking' : 'Expand thinking'}
      className={cn(
        'inline-flex cursor-pointer items-center gap-1 transition-opacity',
        'hover:opacity-80 focus-visible:opacity-80'
      )}
      onClick={onToggle}
      type="button"
    >
      <span className={textClass}>{label}</span>
      {isStreaming ? <AnimatedDots paused={false} /> : null}
      <ChevronRightIcon
        aria-hidden="true"
        className={cn(
          'size-3.5 shrink-0 text-muted-foreground transition-transform',
          isOpen ? 'rotate-90 duration-200 ease-out' : 'rotate-0 duration-150 ease-in'
        )}
      />
    </button>
  );
}

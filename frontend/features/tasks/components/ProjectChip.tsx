'use client';

/**
 * Right-aligned project chip rendered on every task row.
 *
 * Pulls its background and text classes from `PROJECT_TONE_CLASSES` so the
 * chip's appearance stays in lockstep with `TaskProject.tone`. Survival-mode
 * flagged tasks override the project's own tone with `destructive` plus a
 * fire emoji prefix — that override happens upstream in the row, this
 * component just paints whatever it's handed.
 */

import { HashIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { PROJECT_TONE_CLASSES } from '../constants';
import type { TaskProjectTone } from '../types';

export interface ProjectChipProps {
  /** Display label rendered to the right of the optional emoji. */
  label: string;
  /** Tint mapping for the chip background and text color. */
  tone: TaskProjectTone;
  /** Optional emoji prefix — used by Survival Mode and any future flagged set. */
  emoji?: string;
  /** When `true`, the chip omits the leading hash glyph (e.g. for the survival-mode badge). */
  hideHash?: boolean;
}

/**
 * Pure presentation. Renders the chip inline so the row's flex layout can
 * push it to the right edge.
 */
export function ProjectChip({ label, tone, emoji, hideHash }: ProjectChipProps): ReactNode {
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-md px-2 font-medium text-xs tracking-tight',
        PROJECT_TONE_CLASSES[tone]
      )}
    >
      {emoji ? <span aria-hidden="true">{emoji}</span> : null}
      {!hideHash && !emoji ? <HashIcon aria-hidden="true" className="size-3 opacity-70" strokeWidth={2.25} /> : null}
      {label}
    </span>
  );
}

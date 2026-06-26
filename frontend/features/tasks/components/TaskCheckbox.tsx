'use client';

/**
 * Round priority-tinted checkbox rendered at the start of every task row.
 *
 * - The visible circle sits inside a 40×40 hit target so it clears the
 *   touch-target floor without inflating the row height.
 * - The priority ring is provided by the parent via the `ringClass` prop
 *   (looked up from `PRIORITY_RING` in `constants.ts`) so this component
 *   stays decoupled from the priority enum.
 * - On click, the checkmark plays a tiny scale + opacity transition to
 *   read as a tactile commit. Honors `motion-reduce:transition-none`.
 */

import { CheckIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface TaskCheckboxProps {
  /** Current completion state — drives both the fill and the checkmark. */
  checked: boolean;
  /** Toggle callback fired on click + Space/Enter activation. */
  onToggle: () => void;
  /** Tailwind ring utility — looked up from `PRIORITY_RING`. */
  ringClass: string;
  /** Optional label used as the accessible name (defaults to "Toggle complete"). */
  ariaLabel?: string;
}

/**
 * Pure presentation. The container owns whether the row is rendered at
 * all (e.g. completed rows fade and unmount upstream); this component
 * just paints the current state.
 */
export function TaskCheckbox({
  checked,
  onToggle,
  ringClass,
  ariaLabel = 'Toggle complete',
}: TaskCheckboxProps): ReactNode {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={checked}
      aria-label={ariaLabel}
      className={cn(
        // 40×40 hit target with the visible circle centered inside.
        'group/check relative flex size-10 shrink-0 cursor-pointer items-center justify-center',
        // Tactile press — clamped at 0.96 per the design rule.
        'transition-transform duration-100 ease-out active:scale-[0.96] motion-reduce:transition-none motion-reduce:active:scale-100',
        'focus-visible:outline-none'
      )}
    >
      <span
        className={cn(
          'flex size-[18px] items-center justify-center rounded-full bg-background',
          ringClass,
          // Group hover bumps the ring opacity slightly so the affordance
          // surfaces without painting a full hover background on the cell.
          'transition-[background-color,box-shadow] duration-150 ease-out',
          checked ? 'bg-foreground text-background' : 'group-hover/check:bg-foreground/[0.04]',
          // Keyboard ring — separate from the priority ring so they layer.
          'group-focus-visible/check:ring-[3px] group-focus-visible/check:ring-ring/50'
        )}
      >
        <CheckIcon
          aria-hidden="true"
          strokeWidth={3}
          className={cn(
            'size-3 transition-[opacity,transform] duration-150 ease-out motion-reduce:transition-none',
            checked
              ? 'scale-100 opacity-100'
              : 'scale-50 opacity-0 group-hover/check:scale-75 group-hover/check:opacity-30'
          )}
        />
      </span>
    </button>
  );
}

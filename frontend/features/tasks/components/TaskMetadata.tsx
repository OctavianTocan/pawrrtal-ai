'use client';

/**
 * Inline metadata strip rendered under a task title.
 *
 * Lays out the due-date pill, optional flag emoji ("survival mode"), and
 * the tag chips in a single horizontal cluster. Stays decoupled from the
 * priority enum — color choices are made upstream by the row.
 */

import { CalendarIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { TagChip } from './TagChip';

export interface TaskMetadataProps {
  /** Pre-formatted due-date label (e.g. `Today 3 PM`, `Mon 5 May`). */
  dueLabel: string | null;
  /**
   * Tone for the due-date pill. `destructive` paints overdue items in red
   * so the urgency reads at a glance; `neutral` is the default.
   */
  dueTone: 'neutral' | 'destructive';
  /** Lower-cased tag list rendered after the due-date pill. */
  tags: readonly string[];
}

/**
 * Pure presentation. The container computes `dueLabel` and `dueTone` from
 * the task's `dueAt` and current time so this component never touches `Date`.
 */
export function TaskMetadata({ dueLabel, dueTone, tags }: TaskMetadataProps): ReactNode {
  if (!dueLabel && tags.length === 0) return null;

  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
      {dueLabel ? (
        <span
          className={cn(
            'inline-flex items-center gap-1 text-[11px] tabular-nums',
            dueTone === 'destructive' ? 'text-destructive-text' : 'text-muted-foreground'
          )}
        >
          <CalendarIcon aria-hidden="true" className="size-3" strokeWidth={2.25} />
          {dueLabel}
        </span>
      ) : null}
      {tags.map((tag) => (
        <TagChip key={tag} label={tag} />
      ))}
    </div>
  );
}

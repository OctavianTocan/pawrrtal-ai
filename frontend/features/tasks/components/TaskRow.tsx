'use client';

/**
 * One task in the rendered list.
 *
 * Layout:
 *   [ checkbox ]  Title                                        [ project chip ]
 *                 Optional one-line description
 *                 [calendar] Due label   #tag #tag #tag
 *
 * The whole row is clickable (opens the detail pane). The checkbox absorbs
 * its own click so toggling done doesn't also open the pane. Hover paints
 * a subtle `bg-foreground/[0.03]` background and reveals a quick-actions
 * cluster on the right edge.
 */

import { MoreHorizontalIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { PRIORITY_RING } from '../constants';
import type { Task, TaskProject } from '../types';
import { ProjectChip } from './ProjectChip';
import { TaskCheckbox } from './TaskCheckbox';
import { TaskMetadata } from './TaskMetadata';

export interface TaskRowProps {
  task: Task;
  /** Project the row will show in its right-aligned chip. */
  project: TaskProject;
  /** Pre-formatted due-date label (or `null` for inbox-style rows). */
  dueLabel: string | null;
  /** Whether the due date is in the past (controls due-pill tint). */
  isOverdue: boolean;
  /** Whether this row is currently the active one in the detail pane. */
  isActive: boolean;
  onToggleComplete: () => void;
  onSelect: () => void;
  onOpenMenu: () => void;
}

/**
 * Pure presentation. The container resolves `project`, `dueLabel`, and the
 * three callbacks before rendering — this component never reaches into
 * mock data or the URL.
 */
export function TaskRow({
  task,
  project,
  dueLabel,
  isOverdue,
  isActive,
  onToggleComplete,
  onSelect,
  onOpenMenu,
}: TaskRowProps): ReactNode {
  const survivalMode = task.flags?.includes('survival-mode') ?? false;

  // Survival-mode flagged tasks override their project's tone with a
  // fire-emoji destructive chip — mirrors the reference screenshot.
  const chipTone = survivalMode ? 'destructive' : project.tone;
  const chipEmoji = survivalMode ? '🔥' : project.emoji;
  const chipLabel = survivalMode ? 'Survival Mode' : project.name;

  return (
    <div
      className={cn(
        'group/row relative flex items-start gap-3 border-foreground/[0.06] border-b py-3 pr-3 pl-2 transition-colors duration-150 ease-out',
        'hover:bg-foreground/[0.025] data-[active]:bg-foreground/[0.04]',
        task.completed && 'opacity-55'
      )}
      data-active={isActive ? '' : undefined}
    >
      {/* The checkbox sits in its own column so its 40×40 hit area doesn't
			    get absorbed into the text click target. */}
      <div className="-ml-1 flex h-6 items-start pt-0.5">
        <TaskCheckbox
          ariaLabel={`Mark "${task.title}" ${task.completed ? 'incomplete' : 'complete'}`}
          checked={task.completed}
          onToggle={onToggleComplete}
          ringClass={PRIORITY_RING[task.priority]}
        />
      </div>

      {/* The title column expands to fill remaining width. The whole column
			    is the click target for opening the detail pane. */}
      <button
        className="group/title min-w-0 flex-1 cursor-pointer text-left focus-visible:outline-none"
        onClick={onSelect}
        type="button"
      >
        <p
          className={cn(
            'text-pretty text-[14px] text-foreground leading-snug transition-colors duration-150 ease-out',
            task.completed && 'text-muted-foreground line-through decoration-foreground/30'
          )}
        >
          {task.title}
        </p>
        {task.description ? (
          <p className="mt-0.5 line-clamp-1 text-[12px] text-muted-foreground leading-snug">{task.description}</p>
        ) : null}
        <TaskMetadata dueLabel={dueLabel} dueTone={isOverdue ? 'destructive' : 'neutral'} tags={task.tags} />
      </button>

      {/* Right edge cluster — project chip + reveal-on-hover overflow. */}
      <div className="flex shrink-0 items-center gap-2 pt-0.5">
        <ProjectChip emoji={chipEmoji} hideHash={survivalMode} label={chipLabel} tone={chipTone} />
        <button
          aria-label="Task actions"
          className={cn(
            'flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-[opacity,background-color] duration-150 ease-out',
            'opacity-0 hover:bg-foreground/[0.06] hover:text-foreground group-hover/row:opacity-100',
            'focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50'
          )}
          onClick={onOpenMenu}
          type="button"
        >
          <MoreHorizontalIcon aria-hidden="true" className="size-4" />
        </button>
      </div>
    </div>
  );
}

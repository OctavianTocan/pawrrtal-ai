'use client';

/**
 * Right-side detail pane that slides in when a task row is selected.
 *
 * Pure presentation — the container resolves the active task and the
 * project chip, then forwards the dismiss callback. The slide animation
 * lives in the wrapping `<aside>` translate class so this file stays free
 * of motion library dependencies.
 */

import { CalendarIcon, FlagIcon, TagIcon, XIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { Task, TaskProject } from '../types';
import { ProjectChip } from './ProjectChip';

export interface TaskDetailPaneProps {
  /** Currently selected task (or `null` when nothing is selected). */
  task: Task | null;
  /** Project the task belongs to — pre-resolved by the container. */
  project: TaskProject | null;
  /** Pre-formatted due-date label (or `null`). */
  dueLabel: string | null;
  /** Whether the due date is in the past — affects label tint. */
  isOverdue: boolean;
  onClose: () => void;
}

/**
 * Pure presentation. The pane stays mounted with `translate-x-full` when
 * idle so the slide animation runs in both directions; the container
 * never unmounts it during a session.
 */
export function TaskDetailPane({ task, project, dueLabel, isOverdue, onClose }: TaskDetailPaneProps): ReactNode {
  const open = task !== null;

  return (
    <aside
      aria-hidden={!open}
      className={cn(
        'absolute inset-y-0 right-0 flex w-[360px] flex-col border-l border-border bg-background transition-transform duration-[220ms] ease-out motion-reduce:transition-none',
        open ? 'translate-x-0 shadow-[var(--shadow-panel-floating)]' : 'pointer-events-none translate-x-full'
      )}
      style={{
        // Sheet/drawer ease-in-quint per DESIGN.md when collapsing.
        transitionTimingFunction: open ? 'cubic-bezier(0.16, 1, 0.3, 1)' : 'cubic-bezier(0.7, 0, 0.84, 0)',
      }}
    >
      {task ? (
        <TaskDetailBody task={task} project={project} dueLabel={dueLabel} isOverdue={isOverdue} onClose={onClose} />
      ) : null}
    </aside>
  );
}

interface TaskDetailBodyProps {
  task: Task;
  project: TaskProject | null;
  dueLabel: string | null;
  isOverdue: boolean;
  onClose: () => void;
}

/**
 * Inner body — split out from {@link TaskDetailPane} so the wrapper stays
 * trivially simple and the populated form lives in its own readable unit.
 */
function TaskDetailBody({ task, project, dueLabel, isOverdue, onClose }: TaskDetailBodyProps): ReactNode {
  const survivalMode = task.flags?.includes('survival-mode') ?? false;

  return (
    <>
      <header className="flex items-center justify-between gap-2 border-b border-foreground/[0.08] px-5 py-4">
        <div className="flex min-w-0 items-center gap-2">
          {project ? (
            <ProjectChip
              label={survivalMode ? 'Survival Mode' : project.name}
              tone={survivalMode ? 'destructive' : project.tone}
              emoji={survivalMode ? '🔥' : project.emoji}
              hideHash={survivalMode}
            />
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close task detail"
          className="flex size-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors duration-150 ease-out hover:bg-foreground/[0.05] hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
        >
          <XIcon aria-hidden="true" className="size-4" />
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5">
        <div>
          <h2 className="font-display text-[22px] leading-tight font-medium tracking-tight text-balance text-foreground">
            {task.title}
          </h2>
          {task.description ? (
            <p className="mt-3 text-[13px] leading-relaxed text-pretty text-muted-foreground">{task.description}</p>
          ) : (
            <p className="mt-3 text-[13px] text-muted-foreground/70 italic">
              No description yet. Click the row to add one.
            </p>
          )}
        </div>

        <dl className="flex flex-col gap-3 border-t border-foreground/[0.06] pt-4">
          <DetailRow icon={CalendarIcon} label="Due">
            <DueValue dueLabel={dueLabel} isOverdue={isOverdue} />
          </DetailRow>
          <DetailRow icon={FlagIcon} label="Priority">
            <span className="capitalize">{task.priority}</span>
          </DetailRow>
          <DetailRow icon={TagIcon} label="Tags">
            <TagList tags={task.tags} />
          </DetailRow>
        </dl>
      </div>

      <footer className="flex items-center justify-between border-t border-foreground/[0.08] px-5 py-4 text-[12px] text-muted-foreground">
        <span>Edit (mock)</span>
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer rounded-md px-3 py-1.5 text-[12px] font-medium text-foreground transition-colors duration-150 ease-out hover:bg-foreground/[0.06] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
        >
          Close task details
        </button>
      </footer>
    </>
  );
}

/**
 * Due-value renderer. Tints destructive when overdue, italic muted when
 * absent. Extracted so the parent dl reads as a flat list of `DetailRow`s.
 */
function DueValue({ dueLabel, isOverdue }: { dueLabel: string | null; isOverdue: boolean }): ReactNode {
  if (!dueLabel) {
    return <span className="text-muted-foreground italic">No due date</span>;
  }
  return (
    <span className={cn('tabular-nums', isOverdue ? 'text-destructive-text' : 'text-foreground')}>{dueLabel}</span>
  );
}

/**
 * Tag list renderer. Italic muted when empty, chip cluster otherwise.
 */
function TagList({ tags }: { tags: readonly string[] }): ReactNode {
  if (tags.length === 0) {
    return <span className="text-muted-foreground italic">No tags</span>;
  }
  return (
    <span className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex h-5 items-center rounded-md bg-foreground/[0.05] px-1.5 text-[11px] font-medium text-muted-foreground"
        >
          <span aria-hidden="true" className="opacity-60">
            #
          </span>
          {tag}
        </span>
      ))}
    </span>
  );
}

interface DetailRowProps {
  icon: typeof CalendarIcon;
  label: string;
  children: ReactNode;
}

function DetailRow({ icon: Icon, label, children }: DetailRowProps): ReactNode {
  return (
    <div className="flex items-start gap-3">
      <Icon aria-hidden="true" className="mt-0.5 size-3.5 text-muted-foreground" strokeWidth={2.25} />
      <div className="flex min-w-0 flex-1 items-start justify-between gap-2 text-[13px]">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className="min-w-0 text-right text-foreground">{children}</dd>
      </div>
    </div>
  );
}

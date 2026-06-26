'use client';

/**
 * Pure-derivation hook for the Tasks container.
 *
 * Takes the raw seed + the locally-completed set, plus the active view and
 * project, and returns everything the View needs in render-ready shape:
 *  - `sections` — binned + sorted task groups for the active view.
 *  - `dueLabels` / `overdueIds` — pre-formatted per-task metadata.
 *  - `listCounts` / `projectCounts` — sidebar tallies.
 *  - `pageMeta` — title + subtitle for the editorial header.
 *
 * Pulling this out of the container keeps that file focused on URL +
 * event-handler wiring and leaves the math testable in isolation later.
 */

import { useMemo } from 'react';
import { TASK_VIEWS } from './constants';
import {
  buildInboxSections,
  buildTodaySections,
  buildUpcomingSections,
  formatDueLabel,
  isOverdue,
  priorityWeight,
} from './format-utils';
import { TASK_PROJECTS } from './mock-data';
import type { Task, TaskProject, TaskSectionData, TaskViewId } from './types';

/**
 * Pre-resolved metadata for the page header.
 */
export interface TasksPageMeta {
  title: string;
  subtitle: string;
}

/**
 * Result bag produced by {@link useTasksDerivations}.
 */
export interface TasksDerivations {
  sections: readonly TaskSectionData[];
  dueLabels: ReadonlyMap<string, string>;
  overdueIds: ReadonlySet<string>;
  listCounts: Readonly<Partial<Record<TaskViewId, number>>>;
  projectCounts: Readonly<Record<string, number>>;
  pageMeta: TasksPageMeta;
}

interface UseTasksDerivationsArgs {
  workingTasks: readonly Task[];
  activeView: TaskViewId;
  activeProjectId: string | null;
  knownProject: TaskProject | null;
  now: Date;
  onReschedule: () => void;
}

/**
 * Pure derivations — every output is recomputed only when its inputs change.
 * No side effects, no router calls; safe to wrap in `useMemo` at call sites
 * even with the rest of the world holding stale closures.
 */
export function useTasksDerivations(args: UseTasksDerivationsArgs): TasksDerivations {
  const { workingTasks, activeView, activeProjectId, knownProject, now, onReschedule } = args;

  const sections = useMemo<readonly TaskSectionData[]>(
    () =>
      buildSectionsForView({
        workingTasks,
        activeView,
        activeProjectId,
        knownProject,
        now,
        onReschedule,
      }),
    [activeProjectId, activeView, knownProject, now, onReschedule, workingTasks]
  );

  const dueLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const task of workingTasks) {
      if (task.dueAt) map.set(task.id, formatDueLabel(task.dueAt, now));
    }
    return map;
  }, [now, workingTasks]);

  const overdueIds = useMemo(() => {
    const set = new Set<string>();
    for (const task of workingTasks) {
      if (task.dueAt && isOverdue(task.dueAt, now)) set.add(task.id);
    }
    return set;
  }, [now, workingTasks]);

  const listCounts = useMemo(() => buildListCounts(workingTasks, now), [now, workingTasks]);

  const projectCounts = useMemo(() => buildProjectCounts(workingTasks), [workingTasks]);

  const pageMeta = useMemo(
    () => buildPageMeta({ activeProjectId, activeView, knownProject, sections, workingTasks }),
    [activeProjectId, activeView, knownProject, sections, workingTasks]
  );

  return { sections, dueLabels, overdueIds, listCounts, projectCounts, pageMeta };
}

interface BuildSectionsArgs {
  workingTasks: readonly Task[];
  activeView: TaskViewId;
  activeProjectId: string | null;
  knownProject: TaskProject | null;
  now: Date;
  onReschedule: () => void;
}

function buildSectionsForView(args: BuildSectionsArgs): readonly TaskSectionData[] {
  const { workingTasks, activeView, activeProjectId, knownProject, now, onReschedule } = args;

  if (activeProjectId) {
    return buildProjectSection(workingTasks, activeProjectId, knownProject?.name ?? 'Project');
  }
  if (activeView === TASK_VIEWS.today) {
    return buildTodaySections(workingTasks, now, onReschedule);
  }
  if (activeView === TASK_VIEWS.upcoming) {
    return buildUpcomingSections(workingTasks, now);
  }
  if (activeView === TASK_VIEWS.inbox) {
    return buildInboxSections(workingTasks);
  }
  if (activeView === TASK_VIEWS.completed) {
    const completed = workingTasks.filter((task) => task.completed);
    if (completed.length === 0) return [];
    return [
      {
        id: 'completed',
        label: 'Completed',
        subtitle: 'Marked done in this session',
        tasks: completed,
      },
    ];
  }
  return [];
}

function buildProjectSection(
  workingTasks: readonly Task[],
  activeProjectId: string,
  label: string
): readonly TaskSectionData[] {
  const projectTasks = workingTasks.filter((task) => task.projectId === activeProjectId && !task.completed);
  if (projectTasks.length === 0) return [];

  return [
    {
      id: `project-${activeProjectId}`,
      label,
      subtitle: `${projectTasks.length} open`,
      tasks: projectTasks.toSorted((a, b) => {
        const weight = priorityWeight(a.priority) - priorityWeight(b.priority);
        if (weight !== 0) return weight;
        return (a.dueAt?.getTime() ?? Number.POSITIVE_INFINITY) - (b.dueAt?.getTime() ?? Number.POSITIVE_INFINITY);
      }),
    },
  ];
}

function isToday(date: Date, now: Date): boolean {
  return (
    date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
  );
}

function buildListCounts(workingTasks: readonly Task[], now: Date): Partial<Record<TaskViewId, number>> {
  let todayCount = 0;
  let upcomingCount = 0;
  let inboxCount = 0;
  let completedCount = 0;

  for (const task of workingTasks) {
    if (task.completed) {
      completedCount += 1;
      continue;
    }
    if (task.dueAt === null) {
      inboxCount += 1;
      continue;
    }
    if (isOverdue(task.dueAt, now) || isToday(task.dueAt, now)) {
      todayCount += 1;
    } else {
      upcomingCount += 1;
    }
  }

  return {
    [TASK_VIEWS.today]: todayCount,
    [TASK_VIEWS.upcoming]: upcomingCount,
    [TASK_VIEWS.inbox]: inboxCount,
    [TASK_VIEWS.completed]: completedCount,
  };
}

function buildProjectCounts(workingTasks: readonly Task[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const project of TASK_PROJECTS) {
    counts[project.id] = workingTasks.filter((task) => task.projectId === project.id && !task.completed).length;
  }
  return counts;
}

interface PageMetaArgs {
  activeProjectId: string | null;
  activeView: TaskViewId;
  knownProject: TaskProject | null;
  sections: readonly TaskSectionData[];
  workingTasks: readonly Task[];
}

function buildPageMeta(args: PageMetaArgs): TasksPageMeta {
  const { activeProjectId, activeView, knownProject, sections, workingTasks } = args;

  if (activeProjectId && knownProject) {
    const total = workingTasks.filter((task) => task.projectId === knownProject.id && !task.completed).length;
    return {
      title: knownProject.name,
      subtitle: `${total} open ${total === 1 ? 'task' : 'tasks'}`,
    };
  }
  if (activeView === TASK_VIEWS.today) {
    const total = sections.reduce((sum, section) => sum + section.tasks.length, 0);
    return { title: 'Today', subtitle: `${total} ${total === 1 ? 'task' : 'tasks'}` };
  }
  if (activeView === TASK_VIEWS.upcoming) {
    const total = sections.reduce((sum, section) => sum + section.tasks.length, 0);
    return {
      title: 'Upcoming',
      subtitle: `${total} scheduled across the next few days`,
    };
  }
  if (activeView === TASK_VIEWS.inbox) {
    const total = sections.reduce((sum, section) => sum + section.tasks.length, 0);
    return { title: 'Inbox', subtitle: `${total} undated ${total === 1 ? 'idea' : 'ideas'}` };
  }
  const completedTotal = workingTasks.filter((task) => task.completed).length;
  return {
    title: 'Completed',
    subtitle: `${completedTotal} ${completedTotal === 1 ? 'task' : 'tasks'} marked done this session`,
  };
}

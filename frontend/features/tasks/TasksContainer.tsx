'use client';

/**
 * Container for the Tasks surface.
 *
 * Owns:
 *  - URL state parsing (`?view=`).
 *  - Mock data lookup (project list + seed tasks).
 *  - Local mock state (which task is selected, which sections collapsed,
 *    which task ids are marked complete) — all in-memory + localStorage.
 *  - Translation of UI events into `router.replace` calls so the URL
 *    stays the source of truth.
 *
 * All section binning, label formatting, and count math lives in
 * {@link useTasksDerivations}. Renders the pure {@link TasksView} with
 * everything pre-resolved.
 */

import { useRouter, useSearchParams } from 'next/navigation';
import { type ReactNode, Suspense, useCallback, useMemo, useState } from 'react';
import { usePersistedState } from '@/hooks/use-persisted-state';
import { DEFAULT_TASK_VIEW, TASK_QUERY_KEYS, TASK_STORAGE_KEYS, TASK_VIEWS } from './constants';
import { formatDueLabel, isOverdue } from './format-utils';
import { TASK_PROJECTS, TASK_SEED } from './mock-data';
import { TasksView } from './TasksView';
import type { Task, TaskViewId } from './types';
import { useTasksDerivations } from './use-tasks-derivations';
import { useTasksHandlers } from './use-tasks-handlers';

/**
 * Type guard for `?view=` values. Anything matching a known sub-view id
 * resolves to the list views; otherwise the value is treated as a project
 * id and resolved against the project list at render time.
 */
function isTaskViewId(value: string | null): value is TaskViewId {
  if (!value) return false;
  const allowed: readonly string[] = Object.values(TASK_VIEWS);
  return allowed.includes(value);
}

/**
 * Validator for the persisted set of collapsed section IDs. Storage holds
 * an array of strings (sets aren't JSON-friendly); we widen back into a
 * Set inside {@link useCollapsedSections}.
 */
function isStringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

/**
 * Persisted-set helper around `usePersistedState`. The on-disk shape is
 * `string[]` so JSON serialization stays simple; we project to/from a Set
 * for the consumer.
 */
function useCollapsedSections(storageKey: string): {
  value: ReadonlySet<string>;
  toggle: (id: string) => void;
} {
  const [array, setArray] = usePersistedState<readonly string[]>({
    storageKey,
    defaultValue: [],
    validate: isStringArray,
  });

  const value = useMemo(() => new Set(array), [array]);

  const toggle = useCallback(
    (id: string) => {
      setArray((current) => {
        const next = new Set(current);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return Array.from(next);
      });
    },
    [setArray]
  );

  return { value, toggle };
}

/**
 * Container component. Reads the URL, resolves it to render-ready data,
 * and forwards everything to the pure View. Always rendered as a client
 * component because it needs `useSearchParams` and local mock state.
 */
function TasksContainerContent(): ReactNode {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { get } = searchParams;

  // ─── URL state ────────────────────────────────────────────────────────
  const rawView = get(TASK_QUERY_KEYS.view);
  const knownView = isTaskViewId(rawView) ? rawView : null;
  const knownProject = useMemo(
    () => (rawView ? (TASK_PROJECTS.find((project) => project.id === rawView) ?? null) : null),
    [rawView]
  );
  const activeProjectId = knownProject?.id ?? null;
  const activeView: TaskViewId = knownView ?? (activeProjectId ? TASK_VIEWS.today : DEFAULT_TASK_VIEW);

  // ─── Mock state (locally toggled completion + selection) ──────────────
  const [completedIds, setCompletedIds] = usePersistedState<readonly string[]>({
    storageKey: TASK_STORAGE_KEYS.completedTaskIds,
    defaultValue: [],
    validate: isStringArray,
  });
  const completedSet = useMemo(() => new Set(completedIds), [completedIds]);

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  // Per-view collapsed sections — keyed by view so each view remembers
  // its own state independently.
  const collapsedKey = `${TASK_STORAGE_KEYS.collapsedSections}:${activeProjectId ?? activeView}`;
  const collapsedSections = useCollapsedSections(collapsedKey);

  // ─── Compose the working task list with mock completion overrides ────
  const workingTasks = useMemo(
    () => TASK_SEED.map((task) => (completedSet.has(task.id) ? { ...task, completed: true } : task)),
    [completedSet]
  );

  const projectsById = useMemo(() => new Map(TASK_PROJECTS.map((p) => [p.id, p])), []);

  // `now` is captured once at render so all binning + label formatting
  // stays consistent across the same render — keeps DST / timezone edges
  // from drifting between the Overdue and Today sections.
  const now = useMemo(() => new Date(), []);

  const handleReschedule = useCallback(() => {
    // Mock — clear all overdue rows so the "Reschedule" affordance has
    // a satisfying outcome. Real implementation would batch-update due
    // dates server-side.
    setCompletedIds((current) => {
      const next = new Set(current);
      for (const task of workingTasks) {
        if (!task.dueAt) continue;
        if (isOverdue(task.dueAt, now) && !task.completed) {
          next.add(task.id);
        }
      }
      return Array.from(next);
    });
  }, [now, setCompletedIds, workingTasks]);

  const derivations = useTasksDerivations({
    workingTasks,
    activeView,
    activeProjectId,
    knownProject,
    now,
    onReschedule: handleReschedule,
  });

  // ─── Active task resolution ──────────────────────────────────────────
  const activeTask = useMemo<Task | null>(() => {
    if (!selectedTaskId) return null;
    return workingTasks.find((task) => task.id === selectedTaskId) ?? null;
  }, [selectedTaskId, workingTasks]);

  const activeDueLabel = activeTask?.dueAt ? formatDueLabel(activeTask.dueAt, now) : null;
  const activeIsOverdue = activeTask?.dueAt ? isOverdue(activeTask.dueAt, now) : false;

  // ─── Event handlers ──────────────────────────────────────────────────
  const handlers = useTasksHandlers({ router, setSelectedTaskId, setCompletedIds });

  return (
    <TasksView
      activeView={activeView}
      activeProjectId={activeProjectId}
      onSelectView={handlers.handleSelectView}
      onSelectProject={handlers.handleSelectProject}
      title={derivations.pageMeta.title}
      subtitle={derivations.pageMeta.subtitle}
      sections={derivations.sections}
      collapsedSectionIds={collapsedSections.value}
      onToggleCollapsed={collapsedSections.toggle}
      projectsById={projectsById}
      projects={TASK_PROJECTS}
      listCounts={derivations.listCounts}
      projectCounts={derivations.projectCounts}
      activeTask={activeTask}
      activeDueLabel={activeDueLabel}
      activeIsOverdue={activeIsOverdue}
      dueLabels={derivations.dueLabels}
      overdueIds={derivations.overdueIds}
      onToggleComplete={handlers.handleToggleComplete}
      onSelectTask={handlers.handleSelectTask}
      onCloseDetail={handlers.handleCloseDetail}
      onOpenRowMenu={handlers.handleOpenRowMenu}
      onAddTask={handlers.handleAddTask}
      onNew={handlers.handleNew}
    />
  );
}

/**
 * Suspense boundary colocated with the search-param hook so static analysis
 * can see the App Router CSR-bailout guard even when this component is used
 * outside the route entry.
 */
export function TasksContainer(): ReactNode {
  return (
    <Suspense fallback={null}>
      <TasksContainerContent />
    </Suspense>
  );
}

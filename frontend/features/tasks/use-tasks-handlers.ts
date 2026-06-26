'use client';

/**
 * Stable event-handler bag for the Tasks container.
 *
 * Extracted so the container body stays focused on URL + state plumbing
 * and the handler closures live next to the small bit of state they
 * actually capture. All callbacks are stable across renders (the only
 * inputs are setter functions and the router) so re-renders don't churn.
 */

import type { useRouter } from 'next/navigation';
import { type Dispatch, type SetStateAction, useCallback } from 'react';
import { DEFAULT_TASK_VIEW, TASK_QUERY_KEYS } from './constants';
import type { TaskViewId } from './types';

interface UseTasksHandlersArgs {
  router: ReturnType<typeof useRouter>;
  setSelectedTaskId: Dispatch<SetStateAction<string | null>>;
  setCompletedIds: Dispatch<SetStateAction<readonly string[]>>;
}

/**
 * Result bag — every handler is stable across renders.
 */
export interface TasksHandlers {
  handleSelectView: (view: TaskViewId) => void;
  handleSelectProject: (projectId: string) => void;
  handleToggleComplete: (taskId: string) => void;
  handleSelectTask: (taskId: string) => void;
  handleCloseDetail: () => void;
  handleOpenRowMenu: (taskId: string) => void;
  handleAddTask: (title: string) => void;
  handleNew: () => void;
}

/**
 * Builds the stable handler bag for the container. Pure factory — no
 * `useEffect`, no derived state — so it composes cleanly with the
 * derivations hook above.
 */
export function useTasksHandlers(args: UseTasksHandlersArgs): TasksHandlers {
  const { router, setSelectedTaskId, setCompletedIds } = args;

  const navigateTo = useCallback(
    (viewOrProjectId: string) => {
      const params = new URLSearchParams();
      if (viewOrProjectId !== DEFAULT_TASK_VIEW) {
        params.set(TASK_QUERY_KEYS.view, viewOrProjectId);
      }
      const query = params.toString();
      router.replace(query ? `/tasks?${query}` : '/tasks');
      setSelectedTaskId(null);
    },
    [router, setSelectedTaskId]
  );

  const handleSelectView = useCallback((view: TaskViewId) => navigateTo(view), [navigateTo]);
  const handleSelectProject = useCallback((projectId: string) => navigateTo(projectId), [navigateTo]);

  const handleToggleComplete = useCallback(
    (taskId: string) => {
      setCompletedIds((current) => {
        const next = new Set(current);
        if (next.has(taskId)) {
          next.delete(taskId);
        } else {
          next.add(taskId);
        }
        return Array.from(next);
      });
      // Auto-close the detail pane if the row the user just completed was selected.
      setSelectedTaskId((current) => (current === taskId ? null : current));
    },
    [setCompletedIds, setSelectedTaskId]
  );

  const handleSelectTask = useCallback(
    (taskId: string) => setSelectedTaskId((current) => (current === taskId ? null : taskId)),
    [setSelectedTaskId]
  );

  const handleCloseDetail = useCallback(() => setSelectedTaskId(null), [setSelectedTaskId]);

  const handleOpenRowMenu = useCallback(
    (taskId: string) => {
      // Mock — no menu wired yet. Selecting the row is the closest
      // approximation so the click still does *something*.
      setSelectedTaskId(taskId);
    },
    [setSelectedTaskId]
  );

  const handleAddTask = useCallback((_title: string) => {
    // Mock — quick-add is purely visual until a real mutation lands.
  }, []);

  const handleNew = useCallback(() => {
    // Mock — opens nothing today. Wire to an `AppDialog` when the
    // real "new task" flow lands.
  }, []);

  return {
    handleSelectView,
    handleSelectProject,
    handleToggleComplete,
    handleSelectTask,
    handleCloseDetail,
    handleOpenRowMenu,
    handleAddTask,
    handleNew,
  };
}

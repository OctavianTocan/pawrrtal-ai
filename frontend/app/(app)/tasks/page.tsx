/**
 * Tasks route (`/tasks`).
 *
 * Server component that mounts the client {@link TasksContainer} inside the
 * `(app)` route group's existing `AppShell` chrome. All state, URL parsing,
 * and mock-data lookup happens in the container — this file is purely an
 * entry point so the route has a stable boundary.
 *
 * No backend integration yet — the container reads from `mock-data.ts` and
 * persists local UI prefs (collapsed sections, locally-completed task ids)
 * via `usePersistedState`. See `frontend/features/tasks/README` semantics
 * inline in the source for the full View/Container split.
 */

import { Suspense } from 'react';
import { TasksContainer } from '@/features/tasks/TasksContainer';

/**
 * Route entry. Renders the Tasks panel inside the existing app chrome.
 * Wrapped in Suspense because TasksContainer uses useSearchParams(), which
 * requires a Suspense boundary in Next.js App Router to avoid CSR bailout
 * during static generation.
 */
export default function TasksPage(): React.JSX.Element {
  return (
    <Suspense fallback={null}>
      <TasksContainer />
    </Suspense>
  );
}

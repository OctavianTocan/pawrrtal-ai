'use client';

/**
 * Pure presentation shell for the Tasks surface.
 *
 * Receives the resolved view, the section list, the project lookup, and a
 * small set of callbacks. Owns no hooks, no router calls, no data lookup —
 * everything routes back to {@link TasksContainer}.
 *
 * The outer wrapper mirrors the Knowledge surface: a single elevated
 * panel covering the chat-inset slot inside the global app layout.
 */

import { CalendarCheck2Icon, InboxIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { TaskDetailPane } from './components/TaskDetailPane';
import { TaskQuickAdd } from './components/TaskQuickAdd';
import { TaskRow } from './components/TaskRow';
import { TaskSection } from './components/TaskSection';
import { TasksEmptyState } from './components/TasksEmptyState';
import { TasksHeader } from './components/TasksHeader';
import { TasksSubSidebar } from './components/TasksSubSidebar';
import { TASK_VIEWS } from './constants';
import type { Task, TaskProject, TaskSectionData, TaskViewId } from './types';

export interface TasksViewProps {
  activeView: TaskViewId;
  onSelectView: (view: TaskViewId) => void;
  onSelectProject: (projectId: string) => void;

  /** Active project id when the container is showing `?view=<projectId>`. */
  activeProjectId: string | null;

  /** Title rendered in the editorial page header. */
  title: string;
  /** Secondary line under the title (e.g. `22 tasks`). */
  subtitle: string;

  /** Sections already binned + sorted by the container. */
  sections: readonly TaskSectionData[];

  /** Set of section IDs the user has collapsed in this view. */
  collapsedSectionIds: ReadonlySet<string>;
  onToggleCollapsed: (sectionId: string) => void;

  /** Project lookup used by both rows and the detail pane. */
  projectsById: ReadonlyMap<string, TaskProject>;
  /** Full project list for the sub-sidebar. */
  projects: readonly TaskProject[];
  /** Per-list open task counts (for the sidebar). */
  listCounts: Readonly<Partial<Record<TaskViewId, number>>>;
  /** Per-project open task counts (for the sidebar). */
  projectCounts: Readonly<Record<string, number>>;

  /** Active task — opens the detail pane when set. */
  activeTask: Task | null;
  /** Pre-formatted due-date label for the active task. */
  activeDueLabel: string | null;
  /** Whether the active task is overdue. */
  activeIsOverdue: boolean;

  /** Per-task pre-formatted due labels for the row strip. */
  dueLabels: ReadonlyMap<string, string>;
  /** Per-task overdue flags. */
  overdueIds: ReadonlySet<string>;

  onToggleComplete: (taskId: string) => void;
  onSelectTask: (taskId: string) => void;
  onCloseDetail: () => void;
  onOpenRowMenu: (taskId: string) => void;
  onAddTask: (title: string) => void;
  onNew: () => void;
}

/**
 * Pure presentation entry point. The outer wrapper is the elevated panel
 * (`rounded-[14px]`, `shadow-minimal`) that sits inside the chat-inset slot
 * provided by `AppShell`.
 */
export function TasksView(props: TasksViewProps): ReactNode {
  const {
    activeView,
    onSelectView,
    onSelectProject,
    activeProjectId,
    title,
    subtitle,
    sections,
    collapsedSectionIds,
    onToggleCollapsed,
    projectsById,
    projects,
    listCounts,
    projectCounts,
    activeTask,
    activeDueLabel,
    activeIsOverdue,
    dueLabels,
    overdueIds,
    onToggleComplete,
    onSelectTask,
    onCloseDetail,
    onOpenRowMenu,
    onAddTask,
    onNew,
  } = props;

  return (
    // Match the chat home panel: `rounded-surface-lg`, `shadow-panel-floating`,
    // background = `--background-elevated`. Inline style mirrors `ChatView` —
    // the Tailwind `bg-background-elevated` utility was observed to skip
    // hot-reload re-derivations during preset switching, so we anchor the
    // var directly. See `frontend/features/chat/ChatView.tsx`.
    <div
      className="relative flex h-full min-h-0 w-full min-w-0 overflow-hidden rounded-surface-lg shadow-panel-floating"
      style={{ backgroundColor: 'var(--background-elevated)' }}
    >
      <TasksSubSidebar
        activeProjectId={activeProjectId}
        activeView={activeView}
        listCounts={listCounts}
        onNew={onNew}
        onSelectProject={onSelectProject}
        onSelectView={onSelectView}
        projectCounts={projectCounts}
        projects={projects}
      />

      <section className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        <TasksHeader subtitle={subtitle} title={title} />

        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-10">
          {sections.length === 0 ? (
            <TasksEmptyView activeView={activeView} onSelectView={onSelectView} />
          ) : (
            <div className="flex flex-col gap-4">
              <TaskQuickAdd onAdd={onAddTask} />
              <div className="flex flex-col">
                {sections.map((section) => (
                  <TaskSection
                    collapsed={collapsedSectionIds.has(section.id)}
                    key={section.id}
                    onToggleCollapsed={() => onToggleCollapsed(section.id)}
                    section={section}
                  >
                    <ul className="flex flex-col">
                      {section.tasks.map((task) => {
                        const project = projectsById.get(task.projectId);
                        if (!project) return null;
                        return (
                          <li key={task.id}>
                            <TaskRow
                              dueLabel={dueLabels.get(task.id) ?? null}
                              isActive={activeTask?.id === task.id}
                              isOverdue={overdueIds.has(task.id)}
                              onOpenMenu={() => onOpenRowMenu(task.id)}
                              onSelect={() => onSelectTask(task.id)}
                              onToggleComplete={() => onToggleComplete(task.id)}
                              project={project}
                              task={task}
                            />
                          </li>
                        );
                      })}
                    </ul>
                  </TaskSection>
                ))}
              </div>
            </div>
          )}
        </div>

        <TaskDetailPane
          dueLabel={activeDueLabel}
          isOverdue={activeIsOverdue}
          onClose={onCloseDetail}
          project={activeTask ? (projectsById.get(activeTask.projectId) ?? null) : null}
          task={activeTask}
        />
      </section>
    </div>
  );
}

/**
 * Per-view empty state shown when the active sub-view has no rows.
 *
 * Only Today and Inbox get bespoke copy — the other views render the
 * generic empty card so the surface still reads as "intentional empty,"
 * not "404."
 */
function TasksEmptyView({
  activeView,
  onSelectView,
}: {
  activeView: TaskViewId;
  onSelectView: (view: TaskViewId) => void;
}): ReactNode {
  if (activeView === TASK_VIEWS.today) {
    return (
      <TasksEmptyState
        action={{
          label: 'Plan tomorrow',
          onClick: () => onSelectView(TASK_VIEWS.upcoming),
        }}
        description="Nothing on the docket. Take the breather, or pull a few from Upcoming."
        icon={CalendarCheck2Icon}
        title="All clear for today."
      />
    );
  }
  if (activeView === TASK_VIEWS.inbox) {
    return (
      <TasksEmptyState
        description="Stash undated ideas here — they’ll wait for you to triage."
        icon={InboxIcon}
        title="Inbox at zero."
      />
    );
  }
  return (
    <TasksEmptyState
      description="Switch lists, or add a task using the bar above."
      icon={CalendarCheck2Icon}
      title="Nothing here yet."
    />
  );
}

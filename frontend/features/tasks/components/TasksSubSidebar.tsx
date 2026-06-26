'use client';

/**
 * Inner sub-sidebar rendered to the left of the Tasks content area.
 *
 * Distinct from the global app sidebar (which stays visible and continues
 * to host conversations). This sub-sidebar groups Tasks sub-views under
 * two headings — "Lists" (Today / Upcoming / Inbox / Completed) and
 * "Projects" (one row per `TaskProject`) — and surfaces a prominent
 * "New +" pill at the top.
 */

import { ArchiveIcon, CalendarDaysIcon, CalendarIcon, CheckSquareIcon, InboxIcon, PlusIcon } from 'lucide-react';
import type { ComponentType, ReactNode, SVGProps } from 'react';
import { SidebarNavRow } from '@/components/ui/sidebar-nav-row';
import { SidebarSectionHeader } from '@/components/ui/sidebar-section-header';
import { cn } from '@/lib/utils';
import { PROJECT_TONE_CLASSES, TASK_VIEWS } from '../constants';
import type { TaskProject, TaskViewId } from '../types';

interface ListNavItem {
  id: TaskViewId;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Right-aligned counter rendered next to the row (e.g. open-task count). */
  count?: number;
}

export interface TasksSubSidebarProps {
  activeView: TaskViewId;
  onSelectView: (view: TaskViewId) => void;
  onSelectProject: (projectId: string) => void;
  onNew: () => void;
  /** Per-list open task counts — keys are `TaskViewId`s. */
  listCounts: Readonly<Partial<Record<TaskViewId, number>>>;
  /** Project list — rendered under the "Projects" group. */
  projects: readonly TaskProject[];
  /** Per-project open task counts. */
  projectCounts: Readonly<Record<string, number>>;
  /** Active project id when the active view is `?view=<projectId>`. */
  activeProjectId: string | null;
}

/**
 * Pre-defined nav rows for the "Lists" group. Order is meaningful — it
 * matches the order DESIGN.md and the Knowledge sub-sidebar establish for
 * default-then-archive-style flows.
 */
const LIST_NAV_ITEMS: readonly ListNavItem[] = [
  { id: TASK_VIEWS.today, label: 'Today', icon: CalendarIcon },
  { id: TASK_VIEWS.upcoming, label: 'Upcoming', icon: CalendarDaysIcon },
  { id: TASK_VIEWS.inbox, label: 'Inbox', icon: InboxIcon },
  { id: TASK_VIEWS.completed, label: 'Completed', icon: ArchiveIcon },
];

/**
 * Pure presentation. The container owns selection state and translates
 * `onSelectView` / `onSelectProject` into URL pushes. `activeView` and
 * `activeProjectId` arrive pre-resolved.
 */
export function TasksSubSidebar({
  activeView,
  onSelectView,
  onSelectProject,
  onNew,
  listCounts,
  projects,
  projectCounts,
  activeProjectId,
}: TasksSubSidebarProps): ReactNode {
  return (
    <aside className="flex w-[224px] shrink-0 flex-col gap-5 border-r border-border bg-foreground-2 p-3">
      <button
        type="button"
        onClick={onNew}
        className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-full bg-foreground text-[13px] font-medium text-background transition-[background-color,transform] duration-150 ease-out hover:bg-foreground/90 active:scale-[0.98] motion-reduce:transition-none"
      >
        <PlusIcon aria-hidden="true" className="size-4" strokeWidth={2.5} />
        New task
      </button>

      <NavGroup label="Lists">
        {LIST_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = activeProjectId === null && activeView === item.id;
          const count = listCounts[item.id];
          return (
            <NavRow key={item.id} active={active} onClick={() => onSelectView(item.id)} count={count}>
              <Icon aria-hidden="true" className="size-4 text-muted-foreground" strokeWidth={2} />
              {item.label}
            </NavRow>
          );
        })}
      </NavGroup>

      <NavGroup label="Projects">
        {projects.map((project) => {
          const active = activeProjectId === project.id;
          return (
            <NavRow
              key={project.id}
              active={active}
              onClick={() => onSelectProject(project.id)}
              count={projectCounts[project.id] ?? 0}
            >
              {project.emoji ? (
                <span aria-hidden="true" className="text-[13px] leading-none">
                  {project.emoji}
                </span>
              ) : (
                <span
                  aria-hidden="true"
                  className={cn(
                    'inline-flex size-4 items-center justify-center rounded-md text-[10px] font-semibold tracking-tight',
                    PROJECT_TONE_CLASSES[project.tone]
                  )}
                >
                  #
                </span>
              )}
              {project.name}
            </NavRow>
          );
        })}
      </NavGroup>

      <div className="mt-auto flex items-center gap-2 px-1 pt-3 text-[11px] text-muted-foreground/70">
        <CheckSquareIcon aria-hidden="true" className="size-3" strokeWidth={2} />
        <span>Mock data, no backend yet</span>
      </div>
    </aside>
  );
}

interface NavGroupProps {
  label: string;
  children: ReactNode;
}

function NavGroup({ label, children }: NavGroupProps): ReactNode {
  return (
    <div className="flex flex-col gap-1">
      <SidebarSectionHeader label={label} variant="static" />
      <ul className="flex flex-col gap-0.5">{children}</ul>
    </div>
  );
}

interface NavRowProps {
  active: boolean;
  onClick: () => void;
  count?: number;
  children: ReactNode;
}

function NavRow({ active, onClick, count, children }: NavRowProps): ReactNode {
  return (
    <li>
      <SidebarNavRow
        align="center"
        aria-current={active ? 'page' : undefined}
        className="w-full"
        density="compact"
        isSelected={active}
        onClick={onClick}
      >
        <span className="flex flex-1 items-center gap-2 truncate">{children}</span>
        {typeof count === 'number' && count > 0 ? (
          <span
            className={cn(
              'text-[11px] font-medium tabular-nums',
              active ? 'text-foreground/70' : 'text-muted-foreground/80'
            )}
          >
            {count}
          </span>
        ) : null}
      </SidebarNavRow>
    </li>
  );
}

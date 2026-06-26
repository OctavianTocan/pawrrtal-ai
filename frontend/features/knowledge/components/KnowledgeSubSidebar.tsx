'use client';

/**
 * Inner sub-sidebar rendered to the left of the Knowledge content area.
 *
 * Distinct from the global app sidebar (which still owns conversations).
 * This sub-sidebar groups Knowledge sub-views under two headings —
 * "Workspace" (personal) and "Shared" — and surfaces a prominent
 * rounded-pill "New +" button at the top.
 */

import { BrainIcon, FileTextIcon, FolderIcon, PlusIcon, SparklesIcon, UsersIcon } from 'lucide-react';
import type { ComponentType, ReactNode, SVGProps } from 'react';
import { cn } from '@/lib/utils';
import { KNOWLEDGE_VIEWS } from '../constants';
import type { KnowledgeViewId } from '../types';

interface SubSidebarItem {
  id: KnowledgeViewId;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

interface SubSidebarGroup {
  label: string;
  items: readonly SubSidebarItem[];
}

const SUB_SIDEBAR_GROUPS: readonly SubSidebarGroup[] = [
  {
    label: 'Workspace',
    items: [
      { id: KNOWLEDGE_VIEWS.myFiles, label: 'My Files', icon: FolderIcon },
      { id: KNOWLEDGE_VIEWS.memory, label: 'Memory', icon: BrainIcon },
      { id: KNOWLEDGE_VIEWS.skills, label: 'Skills', icon: SparklesIcon },
    ],
  },
  {
    label: 'Shared',
    items: [
      { id: KNOWLEDGE_VIEWS.brainAccess, label: 'Brain access', icon: UsersIcon },
      { id: KNOWLEDGE_VIEWS.sharedWithMe, label: 'Shared with me', icon: FileTextIcon },
      { id: KNOWLEDGE_VIEWS.sharedByMe, label: 'Shared by me', icon: FileTextIcon },
    ],
  },
];

interface KnowledgeSubSidebarProps {
  activeView: KnowledgeViewId;
  onSelectView: (view: KnowledgeViewId) => void;
  onNew: () => void;
}

/**
 * Pure presentation — no hooks, no side effects.
 *
 * The container owns selection state and translates `onSelectView` into a
 * URL push. We pass `activeView` rather than reading any router context
 * so the component stays trivially testable in isolation.
 */
export function KnowledgeSubSidebar({ activeView, onSelectView, onNew }: KnowledgeSubSidebarProps): ReactNode {
  return (
    // Surface chrome (rounded card + shadow + bg) is provided by the
    // containing panel in `KnowledgeView` — this component just paints
    // the row tree inside it.
    <div className="flex h-full min-h-0 w-full flex-col gap-3 p-3">
      <button
        type="button"
        onClick={onNew}
        className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-full bg-foreground-10 text-[13px] font-medium text-foreground transition-colors duration-150 ease-out hover:bg-foreground/15"
      >
        New
        <PlusIcon aria-hidden="true" className="size-4" />
      </button>

      {SUB_SIDEBAR_GROUPS.map((group) => (
        <div key={group.label} className="flex flex-col gap-0.5">
          <div className="px-2 pb-1 text-[12px] font-medium text-muted-foreground">{group.label}</div>
          {group.items.map((item) => {
            const isActive = item.id === activeView;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectView(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'flex h-9 w-full cursor-pointer items-center gap-2 rounded-md px-2 text-left text-[14px] font-medium transition-colors duration-150 ease-out',
                  isActive
                    ? 'bg-foreground-10 text-foreground'
                    : 'text-foreground/80 hover:bg-foreground-5 hover:text-foreground'
                )}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

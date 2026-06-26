'use client';

/**
 * Pure presentation shell for the Knowledge surface.
 *
 * Layout shape (Pawrrtal.ai reference, images #31–#33, #35, #45):
 *
 * - The chat-inset slot hosts TWO sibling elevated panels with a small gap
 *   between them. Each panel is its own rounded-`surface-lg` card with the
 *   `shadow-panel-floating` token + `--background-elevated` surface so it
 *   reads as a separate surface "standing on" the cream page background
 *   instead of one wide card with internal dividers.
 * - The left panel hosts the Knowledge sub-sidebar (`KnowledgeSubSidebar`).
 *   Its surface chrome is provided here, so the inner component is just the
 *   group + row tree.
 * - The right panel hosts the active sub-view (file browser, file list +
 *   document viewer column, memory grid, brain access, shared empty
 *   states). The page-level header strip ("Knowledge / Working / Review ...")
 *   was removed at the user's request — the sub-sidebar's "New +" button
 *   carries the only top-of-surface affordance now.
 *
 * This component is pure — all hooks live in {@link KnowledgeContainer}.
 */

import { BookOpenIcon, FileTextIcon, SparklesIcon, UsersIcon } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import { BrainAccessPanel } from './components/BrainAccessPanel';
import { DocumentViewer } from './components/DocumentViewer';
import { EmptyState } from './components/EmptyState';
import { KnowledgeFileListColumn } from './components/KnowledgeFileListColumn';
import { KnowledgeSubSidebar } from './components/KnowledgeSubSidebar';
import { MemoryCardList } from './components/MemoryCardList';
import { MyFilesPanel } from './components/MyFilesPanel';
import { KNOWLEDGE_VIEWS } from './constants';
import type { KnowledgeBreadcrumb } from './path-utils';
import type { FileTreeNode, KnowledgeViewId, MemoryCardData } from './types';

/**
 * Shared surface for both Knowledge panels. Mirrors the chat panel's
 * `shadow-panel-floating` + `--background-elevated` chrome — same token
 * family the home/chat panel uses, so Knowledge no longer feels like a
 * different design system from the rest of the app.
 *
 * Inline style for the background mirrors `frontend/features/chat/ChatView.tsx`
 * — the `bg-background-elevated` Tailwind utility was observed to occasionally
 * miss hot-reload re-derivations during preset switching.
 */
const PANEL_SURFACE_CLASSNAME =
  'relative flex min-h-0 flex-col overflow-hidden rounded-surface-lg shadow-panel-floating';

const PANEL_SURFACE_STYLE: CSSProperties = {
  backgroundColor: 'var(--background-elevated)',
};

export interface KnowledgeViewProps {
  /** Currently-selected sub-view; drives the sub-sidebar highlight + right pane. */
  activeView: KnowledgeViewId;
  /** Fired when a sub-sidebar row is clicked. */
  onSelectView: (view: KnowledgeViewId) => void;

  /** Currently-resolved tree node when the view is `my-files`. */
  currentNode: FileTreeNode | null;
  /** Crumbs computed by the container; trailing crumb is the current node. */
  crumbs: readonly KnowledgeBreadcrumb[];
  /** Fired when a breadcrumb pill is clicked — passes the target path. */
  onNavigateBreadcrumb: (path: string) => void;
  /** Fired when a folder/file row is activated. */
  onOpenChild: (childName: string, kind: 'file' | 'folder') => void;

  /** Set when the user is viewing an `.md` file inside `my-files`. */
  openFile: { name: string; markdown: string } | null;
  /** Closes the currently-open file (drops the trailing `.md` segment). */
  onCloseFile: () => void;
  /**
   * Called when the user saves an edit in the document viewer. The
   * container is responsible for the network call and should return a
   * promise that rejects on failure so the viewer can show an error banner.
   * If omitted the Edit button is hidden.
   */
  onSaveFile?: (newContent: string) => Promise<void>;

  /** Memory cards for the `memory` view. */
  memoryCards: readonly MemoryCardData[];

  /** Fired by the sub-sidebar's "New +" pill. */
  onNew: () => void;
  /** Fired by the empty-state CTA on Shared views. */
  onShareFromEmptyState: () => void;

  /**
   * When set, this node is rendered _instead of_ the normal `KnowledgeContent`
   * router. Used by the container to show loading spinners or error banners
   * while still keeping the sub-sidebar interactive.
   */
  contentOverride?: ReactNode;
}

/**
 * Returns `true` when every child of the folder is a file. Used to decide
 * whether to render the three-column "leaf folder" layout (file list + doc
 * viewer) or the standard folder grid.
 */
function isLeafFolder(node: FileTreeNode | null): boolean {
  if (node?.kind !== 'folder') return false;
  if (node.children.length === 0) return false;
  return node.children.every((child) => child.kind === 'file');
}

/**
 * Right-pane router. Switches between the file browser, file list +
 * optional document viewer, memory grid, brain access, and the "shared"
 * empty states.
 *
 * Returns either a single content column or a content column plus a
 * trailing document viewer column. The parent decides how to slot them.
 */
function KnowledgeContent(props: KnowledgeViewProps): ReactNode {
  const {
    activeView,
    currentNode,
    crumbs,
    onNavigateBreadcrumb,
    onOpenChild,
    openFile,
    onCloseFile,
    memoryCards,
    onShareFromEmptyState,
  } = props;

  if (activeView === KNOWLEDGE_VIEWS.myFiles) {
    // Leaf folder OR file open inside a leaf folder → three-column shape:
    // sub-sidebar | file-list-column | document-viewer (optional).
    const leaf = isLeafFolder(currentNode);
    if (leaf && currentNode && currentNode.kind === 'folder') {
      return (
        <div className="flex min-h-0 min-w-0 flex-1">
          <KnowledgeFileListColumn
            crumbs={crumbs}
            onNavigateBreadcrumb={onNavigateBreadcrumb}
            files={currentNode.children}
            activeFileName={openFile?.name ?? null}
            onOpenFile={(name) => onOpenChild(name, 'file')}
          />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            {openFile ? (
              <DocumentViewer
                key={openFile.name}
                filename={openFile.name}
                markdown={openFile.markdown}
                onClose={onCloseFile}
                onSave={props.onSaveFile}
              />
            ) : (
              <EmptyState
                icon={FileTextIcon}
                title="Pick a file to read"
                description="Select a file from the list to read it here."
              />
            )}
          </div>
        </div>
      );
    }

    // Standard folder view — sub-folders + files mixed.
    return (
      <MyFilesPanel
        currentNode={currentNode}
        crumbs={crumbs}
        onNavigateBreadcrumb={onNavigateBreadcrumb}
        onOpenChild={onOpenChild}
      />
    );
  }

  if (activeView === KNOWLEDGE_VIEWS.memory) {
    // the Memory landing keeps the cards in a centered column inside
    // the content panel — there's no separate right "preview" pane. We
    // drop the previous 320px split column + empty right pane in favor
    // of a single max-width column that matches reference image #45.
    return (
      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center px-5">
          <span className="rounded-md bg-foreground-5 px-2.5 py-1 text-[13px] font-medium text-foreground">Memory</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6">
          <div className="mx-auto w-full max-w-[560px]">
            <MemoryCardList cards={memoryCards} />
          </div>
        </div>
      </div>
    );
  }

  if (activeView === KNOWLEDGE_VIEWS.skills) {
    return (
      <EmptyState
        icon={SparklesIcon}
        title="Skills coming soon"
        description="Reusable skills will live here once the the skills runtime ships."
      />
    );
  }

  if (activeView === KNOWLEDGE_VIEWS.brainAccess) {
    return <BrainAccessPanel />;
  }

  if (activeView === KNOWLEDGE_VIEWS.sharedWithMe) {
    return (
      <EmptyState
        icon={FileTextIcon}
        title="Nothing shared with you yet."
        description="When someone gives you access to their workspace, their files will land here."
        action={{ label: 'Start sharing', onClick: onShareFromEmptyState }}
      />
    );
  }

  if (activeView === KNOWLEDGE_VIEWS.sharedByMe) {
    return (
      <EmptyState
        icon={UsersIcon}
        title="You haven’t shared anything yet."
        description="Invite a teammate to share files, memory, and skills from your workspace."
        action={{ label: 'Start sharing', onClick: onShareFromEmptyState }}
      />
    );
  }

  // Defensive default — unreachable while `activeView` is correctly typed.
  return (
    <EmptyState
      icon={BookOpenIcon}
      title="Pick a section"
      description="Choose a Knowledge section from the sidebar to get started."
    />
  );
}

/**
 * Top-level shell. Renders the sub-sidebar and the active content section as
 * TWO separate elevated panels with a small gap between them.
 *
 * The outer wrapper has no background AND no `overflow-hidden` — the page
 * background (`bg-sidebar` from `AppShell`) supplies the warm surround,
 * and we deliberately let the panels' drop shadows paint outside this
 * wrapper. The earlier `overflow-hidden` clipped the elevated-panel
 * shadows flush against the wrapper's edges, making the cards read as
 * flat-on-flat against the cream page background.
 */
export function KnowledgeView(props: KnowledgeViewProps): ReactNode {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 gap-3">
      <aside className={`${PANEL_SURFACE_CLASSNAME} w-[224px] shrink-0`} style={PANEL_SURFACE_STYLE}>
        <KnowledgeSubSidebar activeView={props.activeView} onSelectView={props.onSelectView} onNew={props.onNew} />
      </aside>

      <section className={`${PANEL_SURFACE_CLASSNAME} flex-1 min-w-0`} style={PANEL_SURFACE_STYLE}>
        {props.contentOverride ?? <KnowledgeContent {...props} />}
      </section>
    </div>
  );
}

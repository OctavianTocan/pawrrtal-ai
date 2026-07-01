import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, RefObject } from 'react';
import { useRef } from 'react';
import { ProjectsList } from '@/features/projects/components/ProjectsList';
import { useScrollEdges } from '@/hooks/use-scroll-edges';
import type { ConversationGroup } from '@/lib/conversation-groups';
import type { Conversation, ConversationStatus } from '@/lib/types';
import type { ContentSearchResult } from '../hooks/use-conversation-search';
import { ConversationSearchHeader } from './ConversationSearchHeader';
import { NavChatsContent } from './NavChatsContent';

export interface NavChatsViewProps {
  /** Current search input value. */
  searchQuery: string;
  /** Called on every search keystroke. */
  onSearchChange: (query: string) => void;
  /** Called when the user clears the search. */
  onSearchClose: () => void;
  /** Total number of matching conversations. */
  resultCount: number;
  /** Whether conversations are still being fetched. */
  isLoading: boolean;
  /** Whether the data source returned zero conversations. */
  isEmpty: boolean;
  /** Whether the search query is long enough to filter (>= 2 chars). */
  isSearchActive: boolean;
  /** Date-grouped and search-filtered conversation buckets. */
  filteredGroups: ConversationGroup[];
  /** Set of group keys the user has collapsed. */
  collapsedGroups: Set<string>;
  /** Toggles a single group's collapsed state. */
  onToggleGroup: (groupKey: string) => void;
  /** Navigates to the root page to start a new session. */
  onNewSession: () => void;
  /** Navigates to a conversation and closes mobile sidebar. */
  onNavigate: (href: string) => void;
  /** Opens the rename dialog for a conversation. */
  onRename: (conversationId: string) => void;
  /** Opens the delete confirmation for a conversation. */
  onDelete: (conversationId: string) => void;
  /** Toggles archived state for a conversation. */
  onArchive: (conversationId: string) => void;
  /** Toggles flagged state for a conversation. */
  onFlag: (conversationId: string) => void;
  /** Sets the status tag on a conversation. */
  onSetStatus: (conversationId: string, status: ConversationStatus) => void;
  /** Toggles the unread indicator on a conversation. */
  onMarkUnread: (conversationId: string) => void;
  /** Triggers LLM title regeneration for a conversation. */
  onRegenerateTitle: (conversationId: string) => void;
  /** Toggles a single label ID on/off for a conversation. */
  onToggleLabel: (conversationId: string, labelId: string) => void;
  /** Triggers a Markdown download for a conversation. */
  onExportMarkdown: (conversationId: string) => void;
  /** Ref attached to the navigator (listbox) root for focus-zone registration. */
  navigatorRef: RefObject<HTMLDivElement | null>;
  /** Per-conversation search results from content matching. */
  contentSearchResults: Map<string, ContentSearchResult>;
  /** Match info for the currently open chat (searched against loaded messages). */
  activeChatMatchInfo?: { sessionId: string; count: number } | null;
  /** Set of conversation IDs in the current multi-selection. */
  multiSelectedIds: Set<string>;
  /** The conversation ID that should appear keyboard-focused. */
  focusedConversationId: string | null;
  /** Called when a conversation row is clicked (select + navigate). */
  onConversationClick: (conversationId: string, index: number, href: string) => void;
  /** Called on mouseDown for modifier-key multi-select handling. */
  onConversationMouseDown: (event: ReactMouseEvent, conversationId: string, index: number) => void;
  /** Keyboard handler for arrow navigation, range-select, and zone switching. */
  onConversationKeyDown: (event: ReactKeyboardEvent, conversation: Conversation, index: number) => void;
  /** Ref callback to register conversation row elements for programmatic focus. */
  registerConversationElement: (conversationId: string, element: HTMLDivElement | null) => void;
  /** Claims navigator focus zone on mouseDown (before click fires). */
  onNavigatorMouseDown: () => void;
}

export function NavChatsView({
  searchQuery,
  onSearchChange,
  onSearchClose,
  resultCount,
  isLoading,
  isEmpty,
  isSearchActive,
  filteredGroups,
  collapsedGroups,
  onToggleGroup,
  onNewSession,
  onNavigate,
  onRename,
  onDelete,
  onArchive,
  onFlag,
  onSetStatus,
  onMarkUnread,
  onRegenerateTitle,
  onToggleLabel,
  onExportMarkdown,
  navigatorRef,
  contentSearchResults,
  activeChatMatchInfo,
  multiSelectedIds,
  // Pass this down when ConversationRow gets roving tabindex.
  focusedConversationId: _focusedConversationId,
  onConversationClick,
  onConversationMouseDown,
  onConversationKeyDown,
  registerConversationElement,
  onNavigatorMouseDown,
}: NavChatsViewProps): React.JSX.Element {
  // Drives the top/bottom mask-fade gradient on the scroll container —
  // same pattern the prompt textarea uses (`[data-prompt-textarea]` rules
  // in globals.css). The hook reports `canScrollUp` / `canScrollDown` so
  // the CSS can show the gradient only at edges that actually have hidden
  // content, instead of always rendering both edges.
  const scrollRef = useRef<HTMLDivElement>(null);
  const { canScrollUp, canScrollDown } = useScrollEdges(scrollRef);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ConversationSearchHeader
        onSearchChange={onSearchChange}
        onSearchClose={onSearchClose}
        resultCount={resultCount}
        searchQuery={searchQuery}
      />
      {/* Single scroll container for the projects section + the
			    conversation list so they scroll together as one group rather
			    than the projects sticking under the search bar while the
			    chats scroll behind them. `scrollbar-hover` fades the
			    webkit scrollbar in when an ancestor `.group` element is
			    hovered (the sidebar shell — see app-layout.tsx).
			    `data-nav-chats-scroll` + the `data-scroll-up` / `data-scroll-down`
			    attributes drive the top/bottom fade gradients in globals.css
			    so list rows softly fade out when there's more content above
			    or below the visible window. */}
      <div
        className="scrollbar-hover min-h-0 flex-1 overflow-y-auto"
        data-nav-chats-scroll=""
        data-scroll-down={canScrollDown ? 'true' : 'false'}
        data-scroll-up={canScrollUp ? 'true' : 'false'}
        ref={scrollRef}
      >
        {/* Hide the Projects section entirely while the chat list is empty —
				    showing the "Create your first project" CTA alongside the
				    "No sessions yet" empty state looks unpolished, and toggling the
				    Projects header causes the empty-state text to jump up/down. */}
        {!isEmpty && <ProjectsList />}
        <NavChatsContent
          activeChatMatchInfo={activeChatMatchInfo}
          collapsedGroups={collapsedGroups}
          contentSearchResults={contentSearchResults}
          filteredGroups={filteredGroups}
          isEmpty={isEmpty}
          isLoading={isLoading}
          isSearchActive={isSearchActive}
          multiSelectedIds={multiSelectedIds}
          navigatorRef={navigatorRef}
          onArchive={onArchive}
          onConversationClick={onConversationClick}
          onConversationKeyDown={onConversationKeyDown}
          onConversationMouseDown={onConversationMouseDown}
          onDelete={onDelete}
          onExportMarkdown={onExportMarkdown}
          onFlag={onFlag}
          onMarkUnread={onMarkUnread}
          onNavigate={onNavigate}
          onNavigatorMouseDown={onNavigatorMouseDown}
          onNewSession={onNewSession}
          onRegenerateTitle={onRegenerateTitle}
          onRename={onRename}
          onSetStatus={onSetStatus}
          onToggleGroup={onToggleGroup}
          onToggleLabel={onToggleLabel}
          registerConversationElement={registerConversationElement}
          resultCount={resultCount}
          searchQuery={searchQuery}
        />
      </div>
    </div>
  );
}

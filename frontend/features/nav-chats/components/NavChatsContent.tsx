/**
 * @fileoverview Inner content of the conversation list — extracted from
 * `NavChatsView` to keep the parent file under the 500-line repo-wide
 * file-length budget. Renders loading / empty / search-empty states or
 * the grouped, animated conversation rows.
 */

import { Inbox, Search } from 'lucide-react';
import { AnimatePresence, domAnimation, LazyMotion } from 'motion/react';
import * as m from 'motion/react-m';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, RefObject } from 'react';
import { Fragment, useMemo } from 'react';
import type { ConversationGroup } from '@/lib/conversation-groups';
import { highlightMatch } from '@/lib/highlight-match';
import type { Conversation, ConversationStatus } from '@/lib/types';
import type { ContentSearchResult } from '../hooks/use-conversation-search';
import { CollapsibleGroupHeader } from './CollapsibleGroupHeader';
import { ConversationIndicators } from './ConversationIndicators';
import { ConversationLabelBadge } from './ConversationLabelBadge';
import { ConversationSidebarItem } from './ConversationSidebarItem';
import { ConversationsEmptyState } from './ConversationsEmptyState';
import { SearchCountBadge } from './SearchCountBadge';
import { SectionHeader } from './SectionHeader';

/** Enter duration (s) for the date-group expand. DESIGN.md → Motion → Open/close timing. */
const GROUP_EXPAND_ENTER_DURATION = 0.14;
/** Exit duration (s) for the date-group collapse. DESIGN.md → Motion → Open/close timing. */
const GROUP_EXPAND_EXIT_DURATION = 0.1;
/** ease-out-expo — same curve used by the dropdown enter motion. */
const GROUP_EXPAND_ENTER_EASE = [0.16, 1, 0.3, 1] as const;
/** ease-in-quint — same curve used by the dropdown exit motion. */
const GROUP_EXPAND_EXIT_EASE = [0.7, 0, 0.84, 0] as const;
// Scrolling lives on the parent wrapper in NavChatsView so projects and
// conversations scroll as one group. This element keeps listbox semantics and
// the spacing rhythm from the Projects section above.
const CONVERSATION_LIST_CLASS = 'mt-0 pt-1 outline-none';

/**
 * Slice of the parent `NavChatsView` props that the inner content rendering
 * actually consumes. Pulled into its own type so the file is honest about
 * the surface area it owns.
 */
export interface NavChatsContentProps {
  isLoading: boolean;
  isEmpty: boolean;
  isSearchActive: boolean;
  resultCount: number;
  filteredGroups: ConversationGroup[];
  collapsedGroups: Set<string>;
  navigatorRef: RefObject<HTMLDivElement | null>;
  searchQuery: string;
  multiSelectedIds: Set<string>;
  contentSearchResults: Map<string, ContentSearchResult>;
  activeChatMatchInfo?: { sessionId: string; count: number } | null;
  onToggleGroup: (groupKey: string) => void;
  onNewSession: () => void;
  onNavigate: (href: string) => void;
  onRename: (conversationId: string) => void;
  onDelete: (conversationId: string) => void;
  onArchive: (conversationId: string) => void;
  onFlag: (conversationId: string) => void;
  onSetStatus: (conversationId: string, status: ConversationStatus) => void;
  onMarkUnread: (conversationId: string) => void;
  onRegenerateTitle: (conversationId: string) => void;
  onToggleLabel: (conversationId: string, labelId: string) => void;
  onExportMarkdown: (conversationId: string) => void;
  onConversationClick: (conversationId: string, index: number, href: string) => void;
  onConversationMouseDown: (event: ReactMouseEvent, conversationId: string, index: number) => void;
  onConversationKeyDown: (event: ReactKeyboardEvent, conversation: Conversation, index: number) => void;
  registerConversationElement: (conversationId: string, element: HTMLDivElement | null) => void;
  onNavigatorMouseDown: () => void;
}

/** Props for the per-row renderer; derived from the parent slice for consistency. */
type ConversationRowProps = {
  conversation: Conversation;
  index: number;
  visibleIndex: number;
  isSearchActive: boolean;
  searchQuery: string;
  multiSelectedIds: Set<string>;
  contentSearchResults: Map<string, ContentSearchResult>;
  activeChatMatchInfo?: { sessionId: string; count: number } | null;
  onConversationClick: NavChatsContentProps['onConversationClick'];
  onConversationMouseDown: NavChatsContentProps['onConversationMouseDown'];
  onConversationKeyDown: NavChatsContentProps['onConversationKeyDown'];
  registerConversationElement: NavChatsContentProps['registerConversationElement'];
  onNavigate: NavChatsContentProps['onNavigate'];
  onRename: NavChatsContentProps['onRename'];
  onDelete: NavChatsContentProps['onDelete'];
  onArchive: NavChatsContentProps['onArchive'];
  onFlag: NavChatsContentProps['onFlag'];
  onSetStatus: NavChatsContentProps['onSetStatus'];
  onMarkUnread: NavChatsContentProps['onMarkUnread'];
  onRegenerateTitle: NavChatsContentProps['onRegenerateTitle'];
  onToggleLabel: NavChatsContentProps['onToggleLabel'];
  onExportMarkdown: NavChatsContentProps['onExportMarkdown'];
};

/** Renders a single conversation row within a group, computing derived state from search results. */
function ConversationRow({
  conversation,
  index,
  visibleIndex,
  isSearchActive,
  searchQuery,
  multiSelectedIds,
  contentSearchResults,
  activeChatMatchInfo,
  onConversationClick,
  onConversationMouseDown,
  onConversationKeyDown,
  registerConversationElement,
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
}: ConversationRowProps): React.JSX.Element {
  const href = `/c/${conversation.id}`;
  const isSelected = multiSelectedIds.has(conversation.id);
  const searchCount =
    activeChatMatchInfo?.sessionId === conversation.id
      ? activeChatMatchInfo.count
      : contentSearchResults.get(conversation.id)?.matchCount;
  const labels = conversation.labels ?? [];
  const isProcessing = Boolean(conversation.is_processing);
  // Only override the row's left icon slot when the row has live activity
  // (processing spinner, server-side unread meta, plan, queued prompts).
  // Otherwise let `ConversationSidebarItemView`'s status glyph fallback
  // render — that's what makes the colored dot reflect status changes.
  const hasLiveIndicators =
    isProcessing ||
    Boolean(conversation.has_unread_meta) ||
    conversation.last_message_role === 'plan' ||
    (conversation.pending_prompt_count ?? 0) > 0;

  const searchCountBadge = useMemo(
    () =>
      searchCount && searchCount > 0 ? <SearchCountBadge count={searchCount} isSelected={isSelected} /> : undefined,
    [searchCount, isSelected]
  );

  return (
    <ConversationSidebarItem
      id={conversation.id}
      title={isSearchActive ? highlightMatch(conversation.title, searchQuery) : conversation.title}
      updatedAt={conversation.updated_at}
      icon={
        hasLiveIndicators ? (
          <ConversationIndicators conversation={conversation} isProcessing={isProcessing} />
        ) : undefined
      }
      badges={
        labels.length > 0
          ? labels.map((label) => {
              const labelKey = typeof label === 'string' ? label : (label.id ?? label.name);
              return <ConversationLabelBadge key={`${conversation.id}-${labelKey}`} label={label} />;
            })
          : undefined
      }
      titleTrailing={searchCountBadge}
      state={{
        isArchived: conversation.is_archived,
        isFlagged: conversation.is_flagged,
        isInMultiSelect: multiSelectedIds.size > 1 && isSelected,
        isUnread: conversation.is_unread,
        showSeparator: index > 0,
      }}
      onClick={() => onConversationClick(conversation.id, visibleIndex, href)}
      onMouseDown={(event) => onConversationMouseDown(event, conversation.id, visibleIndex)}
      buttonProps={{
        ref: (element: HTMLDivElement | null) => registerConversationElement(conversation.id, element),
        // TODO(#83): tabIndex should be driven by focusedConversationId (roving tabindex)
        // so the keyboard-focused item gets 0 and all others get -1. Currently falls
        // back to isSelected until the orchestration layer wires focusedConversationId
        // through to ConversationRow.
        tabIndex: isSelected ? 0 : -1,
        role: 'option',
        'aria-selected': isSelected,
        onKeyDown: (event: ReactKeyboardEvent) => onConversationKeyDown(event, conversation, visibleIndex),
      }}
      status={conversation.status}
      appliedLabelIds={labels.filter((label): label is string => typeof label === 'string')}
      onNavigate={onNavigate}
      onRename={onRename}
      onDelete={onDelete}
      onArchive={onArchive}
      onFlag={onFlag}
      onSetStatus={onSetStatus}
      onMarkUnread={onMarkUnread}
      onRegenerateTitle={onRegenerateTitle}
      onToggleLabel={onToggleLabel}
      onExportMarkdown={onExportMarkdown}
    />
  );
}

/**
 * Builds the inner content of the conversation list: loading placeholder,
 * empty states, or the grouped conversation rows. Extracted from
 * {@link NavChatsView} to keep the parent file under the project's 500-line
 * file-length budget.
 */
export function NavChatsContent({
  isLoading,
  isEmpty,
  isSearchActive,
  resultCount,
  filteredGroups,
  collapsedGroups,
  navigatorRef,
  searchQuery,
  multiSelectedIds,
  contentSearchResults,
  activeChatMatchInfo,
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
  onConversationClick,
  onConversationMouseDown,
  onConversationKeyDown,
  registerConversationElement,
  onNavigatorMouseDown,
}: NavChatsContentProps): React.JSX.Element | null {
  if (isLoading) {
    return null;
  }

  if (isEmpty) {
    return (
      <ConversationsEmptyState
        icon={<Inbox className="size-4" />}
        title="No sessions yet"
        description="Sessions with your agent appear here. Start one to get going."
        buttonLabel="New Session"
        onAction={onNewSession}
      />
    );
  }

  if (isSearchActive && resultCount === 0) {
    return (
      <ConversationsEmptyState
        icon={<Search className="size-4" />}
        title="No matching sessions"
        description="Try a different title fragment. Search also digs through loaded chat history once you have at least two characters."
      />
    );
  }

  // Pre-compute collapsed state and flat indices outside the JSX to:
  // 1. Avoid duplicated isCollapsible/isCollapsed logic (DRY)
  // 2. Avoid mutable closures that break under React StrictMode
  const canCollapse = !isSearchActive && filteredGroups.length > 1;
  const collapsedKeys = canCollapse ? collapsedGroups : new Set<string>();
  const flatIndexMap = new Map<string, number>();
  let fi = 0;
  for (const group of filteredGroups) {
    if (!collapsedKeys.has(group.key)) {
      for (const conversation of group.items) {
        flatIndexMap.set(conversation.id, fi++);
      }
    }
  }

  return (
    <LazyMotion features={domAnimation}>
      <div
        ref={navigatorRef}
        className={CONVERSATION_LIST_CLASS}
        role="listbox"
        tabIndex={0}
        aria-label="Sessions"
        aria-multiselectable={true}
        onMouseDown={onNavigatorMouseDown}
      >
        <ul className="flex w-full min-w-0 flex-col gap-0">
          {filteredGroups.map((group) => {
            const isCollapsed = collapsedKeys.has(group.key);

            return (
              <Fragment key={group.key}>
                {canCollapse ? (
                  <CollapsibleGroupHeader
                    label={group.label}
                    isCollapsed={isCollapsed}
                    itemCount={group.items.length}
                    onToggle={() => onToggleGroup(group.key)}
                  />
                ) : (
                  <SectionHeader label={group.label} />
                )}
                {/* Animate the group's items in/out on collapse/expand.
							    See file-header note for why height + opacity are
							    interpolated together at GROUP_EXPAND_* timing.
							    Reduced-motion is honored automatically by Motion. */}
                <AnimatePresence initial={false}>
                  {!isCollapsed && (
                    <m.div
                      key={`${group.key}-items`}
                      initial={{ height: 0, opacity: 0 }}
                      animate={{
                        height: 'auto',
                        opacity: 1,
                        transition: {
                          height: {
                            duration: GROUP_EXPAND_ENTER_DURATION,
                            ease: GROUP_EXPAND_ENTER_EASE,
                          },
                          opacity: {
                            duration: GROUP_EXPAND_ENTER_DURATION * 0.85,
                            ease: GROUP_EXPAND_ENTER_EASE,
                          },
                        },
                      }}
                      exit={{
                        height: 0,
                        opacity: 0,
                        transition: {
                          height: {
                            duration: GROUP_EXPAND_EXIT_DURATION,
                            ease: GROUP_EXPAND_EXIT_EASE,
                          },
                          opacity: {
                            duration: GROUP_EXPAND_EXIT_DURATION * 0.85,
                            ease: GROUP_EXPAND_EXIT_EASE,
                          },
                        },
                      }}
                      style={{ overflow: 'hidden' }}
                    >
                      {group.items.map((conversation, index) => (
                        <ConversationRow
                          key={conversation.id}
                          conversation={conversation}
                          index={index}
                          visibleIndex={flatIndexMap.get(conversation.id) ?? 0}
                          isSearchActive={isSearchActive}
                          searchQuery={searchQuery}
                          multiSelectedIds={multiSelectedIds}
                          contentSearchResults={contentSearchResults}
                          activeChatMatchInfo={activeChatMatchInfo}
                          onConversationClick={onConversationClick}
                          onConversationMouseDown={onConversationMouseDown}
                          onConversationKeyDown={onConversationKeyDown}
                          registerConversationElement={registerConversationElement}
                          onNavigate={onNavigate}
                          onRename={onRename}
                          onDelete={onDelete}
                          onArchive={onArchive}
                          onFlag={onFlag}
                          onSetStatus={onSetStatus}
                          onMarkUnread={onMarkUnread}
                          onRegenerateTitle={onRegenerateTitle}
                          onToggleLabel={onToggleLabel}
                          onExportMarkdown={onExportMarkdown}
                        />
                      ))}
                    </m.div>
                  )}
                </AnimatePresence>
              </Fragment>
            );
          })}
        </ul>
      </div>
    </LazyMotion>
  );
}

'use client';

import { useEffect, useMemo, useState } from 'react';
import useGetConversations from '@/hooks/get-conversations';
import type { ConversationGroup } from '@/lib/conversation-groups';
import { buildConversationGroups, countGroupItems, filterConversationGroups } from '@/lib/conversation-groups';
import type { Conversation } from '@/lib/types';
import { NavChatsView } from './components/NavChatsView';
import { ARCHIVED_GROUP_KEY, NAV_CHATS_STORAGE_KEYS } from './constants';
import { ConversationDeleteDialog } from './dialogs/ConversationDeleteDialog';
import { ConversationRenameDialog } from './dialogs/ConversationRenameDialog';
import { useConversationActions } from './hooks/use-conversation-actions';
import { useNavChatsOrchestration } from './hooks/use-nav-chats-orchestration';

/**
 * Reads persisted collapsed group keys from localStorage.
 *
 * Wrapped in try/catch because storage reads can throw in private browsing
 * or when storage access is blocked by browser policy.
 *
 * On first run (no value stored yet) the Archived group defaults to
 * collapsed — Archived is meant to feel out-of-the-way until the user
 * actively reaches for it. After the user toggles it once, the persisted
 * set wins and we honor whatever they chose, even if that's "no entries
 * at all" (Archived expanded by default for them going forward).
 */
function loadCollapsedGroups(): Set<string> {
  if (typeof window === 'undefined') {
    return new Set();
  }

  try {
    const storedGroups = window.localStorage.getItem(NAV_CHATS_STORAGE_KEYS.collapsedGroups);
    if (storedGroups === null) {
      // First run: default the Archived bucket to collapsed.
      return new Set([ARCHIVED_GROUP_KEY]);
    }

    const parsedGroups: unknown = JSON.parse(storedGroups);
    return new Set(Array.isArray(parsedGroups) ? parsedGroups : []);
  } catch {
    return new Set([ARCHIVED_GROUP_KEY]);
  }
}

/**
 * Splits + groups conversations for the sidebar list.
 *
 * Archived rows are partitioned out of the main date-grouped list and
 * appended as a single trailing "Archived" group, but only when the user
 * isn't actively searching (search runs against the active list only).
 *
 * Returned shape stays a simple record so the caller doesn't need to
 * destructure five separate memos.
 */
function useGroupedConversations(
  conversations: Conversation[] | undefined,
  searchQuery: string
): {
  activeConversations: Conversation[];
  archivedConversations: Conversation[];
  filteredGroups: ConversationGroup[];
  resultCount: number;
} {
  const { activeConversations, archivedConversations } = useMemo(() => {
    const active: Conversation[] = [];
    const archived: Conversation[] = [];
    for (const conversation of conversations ?? []) {
      if (conversation.is_archived) {
        archived.push(conversation);
      } else {
        active.push(conversation);
      }
    }
    return { activeConversations: active, archivedConversations: archived };
  }, [conversations]);

  const dateGroups = useMemo(() => buildConversationGroups(activeConversations), [activeConversations]);
  const filteredDateGroups = useMemo(
    () => filterConversationGroups(dateGroups, searchQuery),
    [dateGroups, searchQuery]
  );

  const filteredGroups = useMemo(() => {
    const isSearching = searchQuery.trim().length >= 2;
    if (isSearching || archivedConversations.length === 0) {
      return filteredDateGroups;
    }
    return [
      ...filteredDateGroups,
      {
        key: ARCHIVED_GROUP_KEY,
        label: 'Archived',
        items: archivedConversations,
      },
    ];
  }, [archivedConversations, filteredDateGroups, searchQuery]);

  const resultCount = useMemo(() => countGroupItems(filteredGroups), [filteredGroups]);

  return { activeConversations, archivedConversations, filteredGroups, resultCount };
}

/**
 * Container for the sidebar conversation list.
 *
 * Owns data fetching (conversations), search state, group computation,
 * collapsed-group persistence, navigation, and conversation rename/delete
 * operations. Delegates all rendering to `NavChatsView`.
 */
export function NavChats(): React.JSX.Element {
  const { data: conversations, isLoading } = useGetConversations();

  // --- search ---
  const [searchQuery, setSearchQuery] = useState('');

  // --- grouping & filtering ---
  const { activeConversations, archivedConversations, filteredGroups, resultCount } = useGroupedConversations(
    conversations,
    searchQuery
  );

  // --- collapsed state (persisted in localStorage) ---
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(loadCollapsedGroups);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    try {
      window.localStorage.setItem(NAV_CHATS_STORAGE_KEYS.collapsedGroups, JSON.stringify([...collapsedGroups]));
    } catch {
      // Storage write failed (quota exceeded, private browsing, etc.) — ignore.
    }
  }, [collapsedGroups]);

  const toggleGroupCollapse = (groupKey: string): void => {
    setCollapsedGroups((currentGroups) => {
      const nextGroups = new Set(currentGroups);
      if (nextGroups.has(groupKey)) {
        nextGroups.delete(groupKey);
      } else {
        nextGroups.add(groupKey);
      }
      return nextGroups;
    });
  };

  // --- conversation actions ---
  const {
    renameDialogConversationId,
    deleteDialogConversationId,
    draftTitle,
    isRenamePending,
    isDeletePending,
    setDraftTitle,
    navigateTo,
    handleRenameClick,
    handleDeleteClick,
    handleRenameSubmit,
    handleDeleteConfirm,
    handleRenameDialogOpenChange,
    handleDeleteDialogOpenChange,
    handleArchive,
    handleFlag,
    handleSetStatus,
    handleMarkUnread,
    handleRegenerateTitle,
    handleToggleLabel,
    handleExportMarkdown,
  } = useConversationActions(conversations);

  // --- list orchestration (search, multi-select, keyboard nav, focus refs) ---
  const listOrchestration = useNavChatsOrchestration({
    conversations,
    searchQuery,
    filteredGroups,
    collapsedGroups,
    navigateTo,
    onRenameShortcut: handleRenameClick,
    onArchiveShortcut: handleArchive,
    onDeleteShortcut: handleDeleteClick,
  });

  return (
    <>
      <NavChatsView
        activeChatMatchInfo={listOrchestration.activeChatMatchInfo}
        collapsedGroups={collapsedGroups}
        contentSearchResults={listOrchestration.contentSearchResults}
        filteredGroups={filteredGroups}
        focusedConversationId={listOrchestration.focusedConversationId}
        isEmpty={!activeConversations.length && !archivedConversations.length}
        isLoading={isLoading}
        isSearchActive={listOrchestration.isSearchActive}
        multiSelectedIds={listOrchestration.multiSelectedIds}
        navigatorRef={listOrchestration.navigatorRef}
        onArchive={handleArchive}
        onConversationClick={listOrchestration.onConversationClick}
        onConversationKeyDown={listOrchestration.onConversationKeyDown}
        onConversationMouseDown={listOrchestration.onConversationMouseDown}
        onDelete={handleDeleteClick}
        onExportMarkdown={handleExportMarkdown}
        onFlag={handleFlag}
        onMarkUnread={handleMarkUnread}
        onNavigate={navigateTo}
        onNavigatorMouseDown={listOrchestration.onNavigatorMouseDown}
        onNewSession={() => navigateTo('/')}
        onRegenerateTitle={handleRegenerateTitle}
        onRename={handleRenameClick}
        onSearchChange={setSearchQuery}
        onSearchClose={() => setSearchQuery('')}
        onSetStatus={handleSetStatus}
        onToggleGroup={toggleGroupCollapse}
        onToggleLabel={handleToggleLabel}
        registerConversationElement={listOrchestration.registerConversationElement}
        resultCount={resultCount}
        searchQuery={searchQuery}
      />
      <ConversationRenameDialog
        draftTitle={draftTitle}
        isOpen={!!renameDialogConversationId}
        isPending={isRenamePending}
        onDraftTitleChange={setDraftTitle}
        onOpenChange={handleRenameDialogOpenChange}
        onSubmit={() => void handleRenameSubmit()}
      />
      <ConversationDeleteDialog
        isOpen={!!deleteDialogConversationId}
        isPending={isDeletePending}
        onConfirm={() => void handleDeleteConfirm()}
        onOpenChange={handleDeleteDialogOpenChange}
      />
    </>
  );
}

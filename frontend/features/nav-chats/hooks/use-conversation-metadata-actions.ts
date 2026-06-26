'use client';

import { getLabelById } from '@/features/nav-chats/constants';
import { TOAST_IDS, toast } from '@/lib/toast';
import type { Conversation, ConversationStatus } from '@/lib/types';
import { useRegenerateTitle, useUpdateConversationMetadata } from './use-conversation-mutations';

/** Action handlers returned by {@link useConversationMetadataActions}. */
export interface UseConversationMetadataActionsResult {
  /** Toggles the archived state of a conversation. */
  handleArchive: (conversationId: string) => void;
  /** Toggles the flagged state of a conversation. */
  handleFlag: (conversationId: string) => void;
  /** Sets the status tag on a conversation. */
  handleSetStatus: (conversationId: string, status: ConversationStatus) => void;
  /** Toggles the unread indicator on a conversation. */
  handleMarkUnread: (conversationId: string) => void;
  /** Triggers LLM-based title regeneration for a conversation. */
  handleRegenerateTitle: (conversationId: string) => void;
  /**
   * Toggles a single label ID on a conversation. Adds the ID if missing,
   * removes it if present, then PATCHes the full new label list.
   */
  handleToggleLabel: (conversationId: string, labelId: string) => void;
}

/** Human-readable status copy used in status-change toasts. */
const STATUS_TOAST_LABELS: Record<Exclude<ConversationStatus, null>, string> = {
  todo: 'Todo',
  in_progress: 'In Progress',
  done: 'Done',
};

/** Pull only the string-shaped label IDs out of a row's mixed labels array. */
function extractStringLabelIds(conversation: Conversation): string[] {
  return (conversation.labels ?? []).filter((label): label is string => typeof label === 'string');
}

/**
 * Hook providing archive, flag, status, unread, regenerate-title, and label
 * toggle actions. All handlers fire a PATCH mutation and emit a toast on
 * dispatch (optimistic copy — failure toasts only fire today for regenerate
 * title, where the mutation result is read directly).
 */
export function useConversationMetadataActions(
  conversations: Conversation[] | undefined
): UseConversationMetadataActionsResult {
  const updateMetadataMutation = useUpdateConversationMetadata();
  const regenerateTitleMutation = useRegenerateTitle();

  const handleArchive = (conversationId: string): void => {
    const conversation = conversations?.find((c) => c.id === conversationId);
    if (!conversation) return;
    const nextArchived = !conversation.is_archived;
    void updateMetadataMutation.mutateAsync({
      conversationId,
      is_archived: nextArchived,
    });
    toast.success(nextArchived ? 'Moved to Archive' : 'Restored from Archive', {
      id: TOAST_IDS.conversationArchive,
    });
  };

  const handleFlag = (conversationId: string): void => {
    const conversation = conversations?.find((c) => c.id === conversationId);
    if (!conversation) return;
    const nextFlagged = !conversation.is_flagged;
    void updateMetadataMutation.mutateAsync({
      conversationId,
      is_flagged: nextFlagged,
    });
    toast.success(nextFlagged ? 'Added to your flagged items' : 'Removed from flagged items', {
      id: TOAST_IDS.conversationFlag,
    });
  };

  const handleSetStatus = (conversationId: string, status: ConversationStatus): void => {
    void updateMetadataMutation.mutateAsync({ conversationId, status });
    const message = status === null ? 'Status cleared' : `Status set to ${STATUS_TOAST_LABELS[status]}`;
    toast.success(message, { id: TOAST_IDS.conversationStatus });
  };

  const handleMarkUnread = (conversationId: string): void => {
    const conversation = conversations?.find((c) => c.id === conversationId);
    if (!conversation) return;
    const nextUnread = !conversation.is_unread;
    void updateMetadataMutation.mutateAsync({
      conversationId,
      is_unread: nextUnread,
    });
    toast.success(nextUnread ? 'Marked as unread' : 'Marked as read', {
      id: TOAST_IDS.conversationUnread,
    });
  };

  const handleRegenerateTitle = (conversationId: string): void => {
    toast.loading('Regenerating title...', {
      id: TOAST_IDS.conversationRegenerateTitle,
    });
    regenerateTitleMutation
      .mutateAsync({ conversationId })
      .then((title) => {
        toast.success(title ? `Renamed to "${title}"` : 'Title unchanged', {
          id: TOAST_IDS.conversationRegenerateTitle,
        });
      })
      .catch(() => {
        toast.error('Could not regenerate title', {
          id: TOAST_IDS.conversationRegenerateTitle,
        });
      });
  };

  const handleToggleLabel = (conversationId: string, labelId: string): void => {
    const conversation = conversations?.find((c) => c.id === conversationId);
    if (!conversation) return;

    // Drop legacy structured-label entries while toggling — only string IDs
    // round-trip through the backend's labels[] column. Demo fixtures with
    // inline objects stay intact because they live in static data, not the
    // server's response.
    const currentIds = extractStringLabelIds(conversation);
    const isCurrentlyApplied = currentIds.includes(labelId);
    const nextIds = isCurrentlyApplied ? currentIds.filter((id) => id !== labelId) : [...currentIds, labelId];

    void updateMetadataMutation.mutateAsync({ conversationId, labels: nextIds });

    const label = getLabelById(labelId);
    const labelName = label?.name ?? labelId;
    toast.success(isCurrentlyApplied ? `Removed label "${labelName}"` : `Added label "${labelName}"`, {
      id: TOAST_IDS.conversationLabel,
    });
  };

  return {
    handleArchive,
    handleFlag,
    handleSetStatus,
    handleMarkUnread,
    handleRegenerateTitle,
    handleToggleLabel,
  };
}

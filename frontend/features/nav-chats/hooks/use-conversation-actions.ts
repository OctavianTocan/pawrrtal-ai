'use client';

import { usePathname, useRouter } from 'next/navigation';
import { startTransition, useState } from 'react';
import { useSidebar } from '@/components/ui/sidebar';
import type { Conversation } from '@/lib/types';
import {
  type UseConversationMetadataActionsResult,
  useConversationMetadataActions,
} from './use-conversation-metadata-actions';
import { useDeleteConversation, useRenameConversation } from './use-conversation-mutations';
import { useExportConversation } from './use-export-conversation';

/** Dialog and navigation state returned by {@link useConversationActions}. */
interface UseConversationActionsDialogResult {
  /** The ID of the conversation being renamed, or null if no dialog is open. */
  renameDialogConversationId: string | null;
  /** The ID of the conversation being deleted, or null if no dialog is open. */
  deleteDialogConversationId: string | null;
  /** The current draft title in the rename dialog. */
  draftTitle: string;
  /** Whether the rename mutation is currently pending. */
  isRenamePending: boolean;
  /** Whether the delete mutation is currently pending. */
  isDeletePending: boolean;
  /** Whether any mutation (rename or delete) is currently pending. */
  isMutating: boolean;
  /** Updates the draft title in the rename dialog. */
  setDraftTitle: (title: string) => void;
  /** Navigates to a URL and closes the mobile sidebar. */
  navigateTo: (target: string) => void;
  /** Opens the rename dialog for a conversation (guarded by isMutating). */
  handleRenameClick: (conversationId: string) => void;
  /** Opens the delete confirmation for a conversation (guarded by isMutating). */
  handleDeleteClick: (conversationId: string) => void;
  /** Submits the rename form, validating and calling the mutation. */
  handleRenameSubmit: () => Promise<void>;
  /** Confirms and executes the delete operation, navigating if needed. */
  handleDeleteConfirm: () => Promise<void>;
  /** Handles rename dialog open/close state changes. */
  handleRenameDialogOpenChange: (open: boolean) => void;
  /** Handles delete dialog open/close state changes. */
  handleDeleteDialogOpenChange: (open: boolean) => void;
  /** Triggers a Markdown download for the given conversation by id. */
  handleExportMarkdown: (conversationId: string) => void;
}

/** Full result type combining dialog state with metadata actions. */
export type UseConversationActionsResult = UseConversationActionsDialogResult & UseConversationMetadataActionsResult;

/**
 * Hook to manage conversation rename, delete, and metadata actions.
 *
 * Encapsulates dialog state, mutation calls, navigation, and mobile sidebar
 * closing logic. Metadata actions (archive, flag, status, unread, regenerate
 * title) are delegated to `useConversationMetadataActions`.
 */
export function useConversationActions(conversations: Conversation[] | undefined): UseConversationActionsResult {
  const router = useRouter();
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();
  const renameConversationMutation = useRenameConversation();
  const deleteConversationMutation = useDeleteConversation();
  const metadataActions = useConversationMetadataActions(conversations);
  const { exportAsMarkdown } = useExportConversation();

  const [renameDialogConversationId, setRenameDialogConversationId] = useState<string | null>(null);
  const [deleteDialogConversationId, setDeleteDialogConversationId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');

  const conversationBeingRenamed = conversations?.find(
    (conversation) => conversation.id === renameDialogConversationId
  );

  const closeMobileSidebar = (): void => {
    if (isMobile) setOpenMobile(false);
  };

  const navigateTo = (target: string): void => {
    closeMobileSidebar();
    startTransition(() => {
      router.push(target);
    });
  };

  const isMutating = renameConversationMutation.isPending || deleteConversationMutation.isPending;

  const handleRenameClick = (conversationId: string): void => {
    if (isMutating) return;
    const conversation = conversations?.find((c) => c.id === conversationId);
    if (!conversation) return;
    setDraftTitle(conversation.title);
    setRenameDialogConversationId(conversationId);
  };

  const handleDeleteClick = (conversationId: string): void => {
    if (!isMutating) setDeleteDialogConversationId(conversationId);
  };

  const handleRenameSubmit = async (): Promise<void> => {
    if (!renameDialogConversationId || !conversationBeingRenamed) return;
    const normalizedTitle = draftTitle.trim();
    if (!normalizedTitle || normalizedTitle === conversationBeingRenamed.title) {
      setRenameDialogConversationId(null);
      setDraftTitle('');
      return;
    }
    try {
      await renameConversationMutation.mutateAsync({
        conversationId: renameDialogConversationId,
        title: normalizedTitle,
      });
      setRenameDialogConversationId(null);
      setDraftTitle('');
    } catch {
      // Keep the dialog open so the user can retry.
    }
  };

  const handleDeleteConfirm = async (): Promise<void> => {
    if (!deleteDialogConversationId) return;
    try {
      await deleteConversationMutation.mutateAsync({
        conversationId: deleteDialogConversationId,
      });
      const wasSelected = pathname === `/c/${deleteDialogConversationId}`;
      setDeleteDialogConversationId(null);
      if (wasSelected) navigateTo('/');
    } catch {
      // Keep the dialog open so the user can retry.
    }
  };

  const handleRenameDialogOpenChange = (open: boolean): void => {
    if (!open) {
      setRenameDialogConversationId(null);
      setDraftTitle('');
    }
  };

  const handleDeleteDialogOpenChange = (open: boolean): void => {
    if (!open) setDeleteDialogConversationId(null);
  };

  const handleExportMarkdown = (conversationId: string): void => {
    const conversation = conversations?.find((c) => c.id === conversationId);
    if (!conversation) return;
    void exportAsMarkdown(conversation);
  };

  return {
    renameDialogConversationId,
    deleteDialogConversationId,
    draftTitle,
    isRenamePending: renameConversationMutation.isPending,
    isDeletePending: deleteConversationMutation.isPending,
    isMutating,
    setDraftTitle,
    navigateTo,
    handleRenameClick,
    handleDeleteClick,
    handleRenameSubmit,
    handleDeleteConfirm,
    handleRenameDialogOpenChange,
    handleDeleteDialogOpenChange,
    handleExportMarkdown,
    ...metadataActions,
  };
}

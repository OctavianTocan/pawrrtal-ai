/**
 * React Query mutation: create a conversation row on the server using a client-reserved id.
 *
 * @fileoverview See inline TODO about user-scoped query keys on logout.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/lib/api';
import type { Conversation } from '@/lib/types';
import { useAuthedFetch } from '../../../hooks/use-authed-fetch';

type CreateConversationVariables = {
  title: string;
};

/**
 * Replaces or inserts a conversation at the head of the sidebar list while preserving other rows.
 */
function upsertConversation(
  conversations: Array<Conversation> | undefined,
  conversation: Conversation
): Array<Conversation> {
  const existingConversations = conversations ?? [];
  const withoutConversation = existingConversations.filter((item) => item.id !== conversation.id);

  return [conversation, ...withoutConversation];
}

/**
 * React Query mutation: `POST` a new conversation with the given client-generated id (path) and title (body).
 *
 * Optimistically merges the returned row into `['conversations']` cache and invalidates the list.
 *
 * @param conversationId - UUID reserved on the client that must match the URL/session used for chat.
 */
export function useCreateConversation(conversationId: string) {
  const fetcher = useAuthedFetch();
  const queryClient = useQueryClient();

  return useMutation({
    // TODO: This mutation key should be user-specific to prevent cache pollution
    // when users log out/in. Currently, conversations are cached globally, so a
    // new user logging in might briefly see the previous user's conversations
    // from the React Query cache. Need to either:
    // 1. Clear the query cache on logout/401, OR
    // 2. Make query keys user-specific (requires exposing user ID)
    // See: use-create-conversation.ts:16
    mutationKey: ['conversations'],
    mutationFn: async ({ title }: CreateConversationVariables): Promise<Conversation> => {
      const response = await fetcher(API_ENDPOINTS.conversations.create(conversationId), {
        method: 'POST',
        body: JSON.stringify({ title }),
        headers: {
          'content-type': 'application/json',
        },
      });
      return response.json();
    },
    onSuccess: (conversation) => {
      queryClient.setQueryData<Array<Conversation>>(['conversations'], (conversations) =>
        upsertConversation(conversations, conversation)
      );
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

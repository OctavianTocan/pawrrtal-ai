import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';

/**
 * Triggers backend title generation from the first user message, then refreshes conversation list cache.
 *
 * @param conversationId - Conversation to rename.
 */
export function useGenerateConversationTitle(conversationId: string) {
  const fetcher = useAuthedFetch();
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: ['conversations'],
    mutationFn: async (firstMessage: string) => {
      const response = await fetcher(API_ENDPOINTS.conversations.generateTitle(conversationId, firstMessage), {
        method: 'POST',
        body: JSON.stringify({}),
      });
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

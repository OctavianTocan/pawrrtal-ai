import { API_ENDPOINTS } from '@/lib/api';
import type { Conversation } from '@/lib/types';
import { useAuthedQuery } from './use-authed-query';

/**
 * Fetches the signed-in user's conversation list from `GET /api/v1/conversations`.
 *
 * @returns React Query result with `Conversation[]` data.
 */
export default function useGetConversations() {
  return useAuthedQuery<Conversation[]>(['conversations'], API_ENDPOINTS.conversations.list);
}

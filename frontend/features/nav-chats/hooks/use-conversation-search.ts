/**
 * @file use-conversation-search.ts
 *
 * Full-text search across conversation titles and message content.
 *
 * Title matching uses fuzzy scoring so partial/misspelled queries still surface
 * relevant conversations. Content matching fetches each conversation's message
 * history on-demand and caches it locally so repeated searches don't re-fetch.
 *
 * The cache is capped at MAX_CACHE_SIZE to prevent unbounded memory growth
 * in long-running sessions. Failed fetches are intentionally not cached so
 * transient network errors don't permanently block a conversation from being
 * searchable.
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';
import type { ChatMessage, Conversation } from '@/lib/types';

/**
 * Maximum cached conversation histories. When exceeded, the oldest entry
 * (first inserted) is evicted. Keeps memory bounded in sessions where the
 * user searches many different conversations over time.
 */
const MAX_CACHE_SIZE = 100;

/** Per-conversation search result with match count and a context snippet. */
export type ContentSearchResult = {
  matchCount: number;
  snippet: string;
};

/** Escape special regex characters so user input can be used in a RegExp safely. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Count case-insensitive occurrences of `query` within `content`. */
function countOccurrences(content: string, query: string): number {
  if (!query) {
    return 0;
  }

  const matches = content.match(new RegExp(escapeRegExp(query), 'gi'));
  return matches?.length ?? 0;
}

/** Extract a ~80-char context window around the first match of `query` in `content`. */
function buildSnippet(content: string, query: string): string {
  const matchIndex = content.toLowerCase().indexOf(query.toLowerCase());
  if (matchIndex < 0) {
    return '';
  }

  const start = Math.max(0, matchIndex - 40);
  const end = Math.min(content.length, matchIndex + query.length + 40);
  return content.slice(start, end).trim();
}

/** Concatenate all message contents into a single searchable string. */
function extractSearchableText(messages: ChatMessage[]): string {
  return messages.map((message) => message.content).join('\n');
}

/**
 * Compute a simple fuzzy match score between a title and query.
 * Returns a higher score for exact substring matches, a lower score for
 * subsequence matches, and 0 if the query can't be matched at all.
 */
function fuzzyScore(title: string, query: string): number {
  const lowerTitle = title.toLowerCase();
  const lowerQuery = query.toLowerCase();

  if (lowerTitle.includes(lowerQuery)) {
    return lowerQuery.length * 10;
  }

  let queryIndex = 0;
  let score = 0;

  for (const char of lowerTitle) {
    if (char === lowerQuery[queryIndex]) {
      queryIndex += 1;
      score += 2;
      if (queryIndex === lowerQuery.length) {
        return score;
      }
    }
  }

  return 0;
}

/**
 * Sort conversations by search relevance: title fuzzy score first, then
 * content match count, then recency as a tiebreaker.
 *
 * TODO: Wire activeChatMatchInfo into ranking to boost the active chat
 * when it has content matches (avoids it dropping below closed conversations
 * that happen to mention the query more often).
 */
export function rankConversationsForSearch(
  conversations: Conversation[],
  query: string,
  contentSearchResults: Map<string, ContentSearchResult>
): Conversation[] {
  return [...conversations].sort((left, right) => {
    const leftScore = fuzzyScore(left.title, query);
    const rightScore = fuzzyScore(right.title, query);

    if (leftScore > 0 && rightScore === 0) {
      return -1;
    }

    if (leftScore === 0 && rightScore > 0) {
      return 1;
    }

    if (leftScore !== rightScore) {
      return rightScore - leftScore;
    }

    const leftCount = contentSearchResults.get(left.id)?.matchCount ?? 0;
    const rightCount = contentSearchResults.get(right.id)?.matchCount ?? 0;

    if (leftCount !== rightCount) {
      return rightCount - leftCount;
    }

    return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
  });
}

/**
 * Hook that powers the sidebar search bar. Manages the fetch/cache lifecycle
 * for conversation message histories and computes per-conversation match
 * counts and snippets.
 *
 * @param conversations - The full list of conversations visible in the sidebar.
 * @param searchQuery - Raw text from the search input (trimmed internally).
 * @param activeConversationId - The conversation open in the chat panel (if any).
 * @param activeChatHistory - Messages already loaded for the active chat
 *   (avoids a redundant fetch since the chat panel already has them).
 */
export function useConversationSearch({
  conversations,
  searchQuery,
  activeConversationId,
  activeChatHistory,
}: {
  conversations: Conversation[];
  searchQuery: string;
  activeConversationId?: string | null;
  activeChatHistory?: ChatMessage[];
}) {
  const fetcher = useAuthedFetch();
  const cacheRef = useRef(new Map<string, ChatMessage[]>());
  const [contentSearchResults, setContentSearchResults] = useState<Map<string, ContentSearchResult>>(new Map());
  const trimmedQuery = searchQuery.trim();
  const isSearchActive = trimmedQuery.length >= 2;

  // TODO: Cache keys by conversation.id only. If message content can change under
  // the same ID (edits, deletions), stale results will be returned. Consider keying
  // by id+updated_at or invalidating on mutation if this becomes an issue.

  useEffect(() => {
    if (!isSearchActive) {
      // Avoid setState when already cleared — a fresh `new Map()` every run triggers
      // infinite re-renders when this effect re-executes (e.g. unstable deps).
      setContentSearchResults((previous) => {
        if (previous.size === 0) {
          return previous;
        }
        return new Map();
      });
      return;
    }

    let cancelled = false;

    const computeResults = async () => {
      const missingConversationIds = conversations
        .map((conversation) => conversation.id)
        .filter((conversationId) => !cacheRef.current.has(conversationId));

      // TODO: Promise.all fetches all uncached conversations concurrently. If the
      // conversation list grows large (hundreds+), consider adding a concurrency
      // limiter to avoid overwhelming the backend.
      if (missingConversationIds.length > 0) {
        await Promise.all(
          missingConversationIds.map(async (conversationId) => {
            try {
              const response = await fetcher(API_ENDPOINTS.conversations.getMessages(conversationId));
              const payload = (await response.json()) as ChatMessage[];
              cacheRef.current.set(conversationId, payload);

              // Evict oldest entries if cache exceeds the cap.
              if (cacheRef.current.size > MAX_CACHE_SIZE) {
                const firstKey = cacheRef.current.keys().next().value;
                if (firstKey !== undefined) {
                  cacheRef.current.delete(firstKey);
                }
              }
            } catch {
              // Don't cache failed fetches so the next search retries.
            }
          })
        );
      }

      if (cancelled) {
        return;
      }

      const nextResults = new Map<string, ContentSearchResult>();
      for (const conversation of conversations) {
        const chatHistory = cacheRef.current.get(conversation.id) ?? [];
        const searchableText = extractSearchableText(chatHistory);
        const titleCount = countOccurrences(conversation.title, trimmedQuery);
        const contentCount = countOccurrences(searchableText, trimmedQuery);
        const matchCount = titleCount + contentCount;

        if (matchCount > 0 || conversation.title.toLowerCase().includes(trimmedQuery.toLowerCase())) {
          nextResults.set(conversation.id, {
            matchCount,
            snippet: buildSnippet(searchableText || conversation.title, trimmedQuery),
          });
        }
      }

      setContentSearchResults(nextResults);
    };

    void computeResults();

    return () => {
      cancelled = true;
    };
  }, [conversations, fetcher, isSearchActive, trimmedQuery]);

  const activeChatMatchInfo = useMemo(() => {
    if (!isSearchActive || !activeConversationId || !activeChatHistory) {
      return null;
    }

    const searchableText = extractSearchableText(activeChatHistory);
    const count = countOccurrences(searchableText, trimmedQuery);
    return {
      sessionId: activeConversationId,
      count,
    };
  }, [activeChatHistory, activeConversationId, isSearchActive, trimmedQuery]);

  return {
    contentSearchResults,
    activeChatMatchInfo,
    isSearchActive,
  };
}

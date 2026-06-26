import { describe, expect, it } from 'vitest';
import type { Conversation } from '@/lib/types';
import { type ContentSearchResult, rankConversationsForSearch } from './use-conversation-search';

const mk = (id: string, title: string, updated_at: string): Conversation => ({
  id,
  title,
  user_id: 'u',
  created_at: updated_at,
  updated_at,
  is_archived: false,
  is_flagged: false,
  is_unread: false,
  status: null,
});

describe('rankConversationsForSearch', () => {
  const a = mk('a', 'Alpha launch plan', '2026-01-03T00:00:00Z');
  const b = mk('b', 'Bravo notes', '2026-01-01T00:00:00Z');
  const c = mk('c', 'plan B', '2026-01-02T00:00:00Z');

  it('ranks exact title substring matches above non-matches', () => {
    const ranked = rankConversationsForSearch([a, b, c], 'plan', new Map());
    expect(ranked[0]?.id).toMatch(/^[ac]$/);
    expect(ranked.at(-1)?.id).toBe('b');
  });

  it('breaks ties on equal score by content match count', () => {
    const counts = new Map<string, ContentSearchResult>([
      ['a', { matchCount: 1, snippet: '' }],
      ['c', { matchCount: 5, snippet: '' }],
    ]);
    const ranked = rankConversationsForSearch([a, c], 'plan', counts);
    expect(ranked[0]?.id).toBe('c');
  });

  it('uses recency as the final tiebreaker when scores + counts tie', () => {
    const ranked = rankConversationsForSearch([a, c], 'xyz', new Map());
    // Neither has any matches → recency only — a is more recent.
    expect(ranked[0]?.id).toBe('a');
  });

  it('returns a new array (does not mutate input)', () => {
    const list = [a, b, c];
    const ranked = rankConversationsForSearch(list, 'plan', new Map());
    expect(ranked).not.toBe(list);
  });
});

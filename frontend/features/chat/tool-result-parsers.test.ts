import { describe, expect, it } from 'vitest';
import { extractToolChips } from './tool-result-parsers';

describe('extractToolChips', () => {
  it('returns empty chips when content is not valid JSON', () => {
    const chips = extractToolChips('web_search', 'not-json');
    expect(chips.webSources).toEqual([]);
    expect(chips.calendarEvents).toEqual([]);
    expect(chips.memoryResults).toEqual([]);
  });

  it('parses Anthropic-style web_search citations and dedupes URLs', () => {
    const payload = JSON.stringify([
      { citations: ['https://www.foo.com/a', 'https://www.foo.com/a'] },
      { citations: ['https://bar.com/x'] },
    ]);
    const chips = extractToolChips('web_search', payload);
    expect(chips.webSources.map((s) => s.url)).toEqual(['https://www.foo.com/a', 'https://bar.com/x']);
    expect(chips.webSources[0]?.siteName).toBe('www.foo.com');
    expect(chips.webSources[0]?.faviconUrl).toContain('icons.duckduckgo.com');
  });

  it('parses calendar_search arrays and { events } shapes', () => {
    const event = {
      event_id: 'e1',
      summary: 'Standup',
      start_time: '2026-05-04T10:00:00Z',
      html_link: 'https://cal/e1',
    };
    const arrayShape = extractToolChips('calendar_search', JSON.stringify([event]));
    const wrappedShape = extractToolChips('calendar_search', JSON.stringify({ events: [event] }));
    expect(arrayShape.calendarEvents).toEqual(wrappedShape.calendarEvents);
    expect(arrayShape.calendarEvents[0]?.summary).toBe('Standup');
  });

  it('parses memory_search results into memory chips', () => {
    const payload = JSON.stringify([{ meeting_id: 'm1', title: 'Sprint review', start_time_local: '2026-05-04' }]);
    const chips = extractToolChips('memory_search', payload);
    expect(chips.memoryResults).toEqual([{ meetingId: 'm1', title: 'Sprint review', startTime: '2026-05-04' }]);
  });

  it('parses search_chat_history into truncated memory chips', () => {
    const longText = 'a'.repeat(120);
    const payload = JSON.stringify({
      conversations: [{ session_id: 's1', user_message: longText, timestamp: 't' }],
    });
    const chips = extractToolChips('search_chat_history', payload);
    expect(chips.memoryResults[0]?.meetingId).toBe('s1');
    expect(chips.memoryResults[0]?.title.length).toBeLessThanOrEqual(53);
    expect(chips.memoryResults[0]?.title.endsWith('...')).toBe(true);
  });

  it('returns empty chips for unknown tools', () => {
    const chips = extractToolChips('unknown_tool', '[1,2,3]');
    expect(chips.webSources).toEqual([]);
    expect(chips.calendarEvents).toEqual([]);
    expect(chips.memoryResults).toEqual([]);
  });
});

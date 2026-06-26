import { describe, expect, it } from 'vitest';
import {
  getCompletedToolLabel,
  getToolIcon,
  getToolLabel,
  isMemoryTool,
  KNOWN_TOOL_NAMES,
  MAX_VISIBLE_RESULTS,
} from './thinking-constants';

describe('thinking-constants', () => {
  it('returns the present-tense label for known tools', () => {
    expect(getToolLabel(KNOWN_TOOL_NAMES.WEB_SEARCH)).toBe('Searching the web');
    expect(getToolLabel(KNOWN_TOOL_NAMES.READ_DOCUMENT)).toBe('Reading document');
  });

  it('returns the past-tense label for known tools', () => {
    expect(getCompletedToolLabel(KNOWN_TOOL_NAMES.WEB_SEARCH)).toBe('Searched the web');
    expect(getCompletedToolLabel(KNOWN_TOOL_NAMES.READ_DOCUMENT)).toBe('Read document');
  });

  it('falls back to the raw tool name when unknown', () => {
    expect(getToolLabel('mystery_tool')).toBe('mystery_tool');
    expect(getCompletedToolLabel('mystery_tool')).toBe('mystery_tool');
  });

  it('returns a Lucide icon component for every known tool', () => {
    for (const value of Object.values(KNOWN_TOOL_NAMES)) {
      const Icon = getToolIcon(value);
      expect(typeof Icon).toBe('object'); // forwardRef object
    }
  });

  it('returns a search icon fallback for unknown tools', () => {
    const Icon = getToolIcon('not_a_real_tool');
    expect(Icon).toBeTruthy();
  });

  it('classifies memory-style tools', () => {
    expect(isMemoryTool(KNOWN_TOOL_NAMES.MEMORY_SEARCH)).toBe(true);
    expect(isMemoryTool(KNOWN_TOOL_NAMES.SUMMARY_SEARCH)).toBe(true);
    expect(isMemoryTool(KNOWN_TOOL_NAMES.SEARCH_CHAT_HISTORY)).toBe(true);
    expect(isMemoryTool(KNOWN_TOOL_NAMES.WEB_SEARCH)).toBe(false);
    expect(isMemoryTool('made_up')).toBe(false);
  });

  it('exposes a positive MAX_VISIBLE_RESULTS', () => {
    expect(MAX_VISIBLE_RESULTS).toBeGreaterThan(0);
  });
});

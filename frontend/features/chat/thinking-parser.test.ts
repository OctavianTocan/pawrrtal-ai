import { describe, expect, it } from 'vitest';
import { formatThinkingDuration, parseThinkingSections } from './thinking-parser';

describe('parseThinkingSections', () => {
  it('returns an empty array for an empty input', () => {
    expect(parseThinkingSections('')).toEqual([]);
  });

  it('returns one untitled section for plain prose', () => {
    expect(parseThinkingSections('Hello there')).toEqual([{ title: '', content: 'Hello there' }]);
  });

  it('splits on ## headers and preserves text before the first header', () => {
    const text = ['preamble', '## Plan', 'do step A', '## Execute', 'now do A'].join('\n');
    expect(parseThinkingSections(text)).toEqual([
      { title: '', content: 'preamble' },
      { title: 'Plan', content: 'do step A' },
      { title: 'Execute', content: 'now do A' },
    ]);
  });

  it('recognises **Title** lines as headers', () => {
    const text = '**Plan**\nstep A\n**Execute**\nstep B';
    expect(parseThinkingSections(text)).toEqual([
      { title: 'Plan', content: 'step A' },
      { title: 'Execute', content: 'step B' },
    ]);
  });
});

describe('formatThinkingDuration', () => {
  it('renders sub-second durations as <1s', () => {
    expect(formatThinkingDuration(0)).toBe('Thought for <1s');
    expect(formatThinkingDuration(0.4)).toBe('Thought for <1s');
  });

  it('renders whole-second durations', () => {
    expect(formatThinkingDuration(7)).toBe('Thought for 7s');
  });
});

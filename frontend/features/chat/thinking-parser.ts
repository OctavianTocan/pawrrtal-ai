/**
 * Parse model-streamed reasoning text into rendered sections.
 *
 * @fileoverview Some providers (notably Gemini) format the `thinking` payload
 * with `## Title` headings or `**Title**` bold lines that introduce a logical
 * sub-step. The chain-of-thought renderer surfaces each sub-step as its own
 * bulleted item, and falls back to a single section when the input is plain
 * prose. Headers and content are preserved verbatim — we don't re-render the
 * inner markdown here, the caller does that via Streamdown.
 */

/** A reasoning section parsed out of a `thinking` block. */
export interface ThinkingSection {
  /** Header text — empty string for content that appeared before any header. */
  title: string;
  /** Trimmed body content of the section. */
  content: string;
}

/**
 * Split a thinking text block into ordered sections.
 *
 * Recognises `## Title` and `### Title` ATX headings as well as a leading
 * `**Title**` bold line on its own. Anything before the first header (or the
 * whole input if no headers exist) becomes a section with an empty `title` so
 * the renderer can choose to render it as plain prose.
 */
export function parseThinkingSections(text: string): ThinkingSection[] {
  if (!text) return [];

  const headerPattern = /^(?:\*\*([^*\n]+)\*\*[ \t]*$|#{2,3}\s+(.+?)[ \t]*)$/gm;
  const headers: Array<{ title: string; index: number; endIndex: number }> = [];
  let match: RegExpExecArray | null = headerPattern.exec(text);
  while (match !== null) {
    const captured = match[1] ?? match[2] ?? '';
    const title = captured.trim();
    headers.push({
      title,
      index: match.index,
      endIndex: match.index + match[0].length,
    });
    match = headerPattern.exec(text);
  }

  if (headers.length === 0) {
    const trimmed = text.trim();
    return trimmed ? [{ title: '', content: trimmed }] : [];
  }

  const sections: ThinkingSection[] = [];
  const firstHeaderIndex = headers[0]?.index ?? 0;
  if (firstHeaderIndex > 0) {
    const preamble = text.slice(0, firstHeaderIndex).trim();
    if (preamble) sections.push({ title: '', content: preamble });
  }

  for (let i = 0; i < headers.length; i++) {
    const header = headers[i];
    if (!header) continue;
    const next = headers[i + 1];
    const contentStart = header.endIndex;
    const contentEnd = next ? next.index : text.length;
    sections.push({
      title: header.title,
      content: text.slice(contentStart, contentEnd).trim(),
    });
  }

  return sections;
}

/**
 * Format a duration in seconds as the label shown on the reasoning panel
 * trigger. Uses established wording so the UX feels familiar.
 */
export function formatThinkingDuration(seconds: number): string {
  if (seconds < 1) return 'Thought for <1s';
  return `Thought for ${seconds}s`;
}

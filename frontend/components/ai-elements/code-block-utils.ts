/**
 * Utility functions for syntax-highlighted code blocks.
 *
 * @fileoverview Extracted from `code-block.tsx` so component files only
 * export React components (react-doctor `only-export-components`).
 */

import { type BundledLanguage, codeToTokens } from 'shiki';

export type HighlightedToken = {
  content: string;
  color?: string;
  bgColor?: string;
  fontStyle?: number;
};

export type HighlightedCode = {
  tokens: HighlightedToken[][];
};

/** Highlight code using Shiki for both light and dark themes. */
export async function highlightCode(
  code: string,
  language: BundledLanguage
): Promise<[HighlightedCode, HighlightedCode]> {
  return await Promise.all([
    codeToTokens(code, {
      lang: language,
      theme: 'one-light',
    }),
    codeToTokens(code, {
      lang: language,
      theme: 'one-dark-pro',
    }),
  ]);
}

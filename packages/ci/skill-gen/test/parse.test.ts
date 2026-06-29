import { describe, expect, test } from 'vitest';
import type { ParsedSkillFragment } from '../src/parse';
import { parseFragment } from '../src/parse';
import type { RawFragment } from '../src/scan';

/**
 * Builds a raw fragment around parser input lines.
 * @param lines Fragment lines to parse.
 * @param relativePath Path used for template expansion.
 * @returns A raw fragment with a stable file path.
 */
function rawFragment(lines: string[], relativePath = 'packages/example/src/module.ts'): RawFragment {
  return {
    lines,
    filePath: `/repo/${relativePath}`,
    relativePath,
  };
}

/**
 * Narrows a parse result for assertions.
 * @param fragment Fragment result returned by the parser.
 * @returns The parsed fragment when parsing succeeded.
 */
function expectParsed(fragment: ParsedSkillFragment | null): ParsedSkillFragment {
  if (fragment === null) {
    throw new Error('Expected fragment to parse.');
  }

  return fragment;
}

describe('parseFragment', () => {
  test('parses frontmatter and body from slash comment fragments', () => {
    const fragment = parseFragment(
      rawFragment([
        '// ---',
        '// name: slash-skill',
        '// description: "Slash comment skill."',
        '// ---',
        '//',
        '// # Slash Body',
        '//',
        '// Body text.',
      ])
    );

    expect(expectParsed(fragment)).toEqual({
      name: 'slash-skill',
      description: 'Slash comment skill.',
      extraFrontmatter: [],
      body: '# Slash Body\n\nBody text.',
      relativePath: 'packages/example/src/module.ts',
    });
  });

  test('parses frontmatter and body from hash comment fragments', () => {
    const fragment = parseFragment(
      rawFragment([
        '# ---',
        '# name: hash-skill',
        '# description: Hash comment skill.',
        '# ---',
        '#',
        '# # Hash Body',
        '#',
        '# Body text.',
      ])
    );

    expect(expectParsed(fragment)).toEqual({
      name: 'hash-skill',
      description: 'Hash comment skill.',
      extraFrontmatter: [],
      body: '# Hash Body\n\nBody text.',
      relativePath: 'packages/example/src/module.ts',
    });
  });

  test('preserves additional frontmatter lines for generated output', () => {
    const fragment = parseFragment(
      rawFragment([
        '// ---',
        '// name: path-skill',
        '// description: Skill with path triggers.',
        '// paths:',
        '//   - "backend/**/*.py"',
        '//   - "frontend/**/*.tsx"',
        '// ---',
        '//',
        '// Body.',
      ])
    );

    expect(expectParsed(fragment)).toMatchObject({
      name: 'path-skill',
      description: 'Skill with path triggers.',
      extraFrontmatter: ['paths:', '  - "backend/**/*.py"', '  - "frontend/**/*.tsx"'],
      body: 'Body.',
    });
  });

  test('allows leading blank lines before frontmatter', () => {
    const fragment = parseFragment(
      rawFragment([
        '//',
        '//   ',
        '// ---',
        '// name: blank-leading',
        '// description: Blank leading lines.',
        '// ---',
        '//',
        '// Body after leading blank lines.',
      ])
    );

    expect(expectParsed(fragment).body).toBe('Body after leading blank lines.');
  });

  test('expands path templates and preserves escaped template literals', () => {
    const fragment = parseFragment(
      rawFragment([
        '// ---',
        '// name: template-skill',
        '// description: Template skill.',
        '// ---',
        '//',
        '// File: $$file',
        '// Directory: $$directory',
        '// Literal file: \\$$file',
        '// Literal directory: \\$$directory',
      ])
    );

    expect(expectParsed(fragment).body).toBe(
      [
        'File: packages/example/src/module.ts',
        'Directory: packages/example/src',
        'Literal file: $$file',
        'Literal directory: $$directory',
      ].join('\n')
    );
  });

  test('returns null for fragments without usable skill frontmatter', () => {
    const invalidFragments = [
      rawFragment(['// ---', '// description: Missing name.', '// ---', '// Body.']),
      rawFragment(['// ---', '// name: missing-description', '// ---', '// Body.']),
      rawFragment(['// name: no-frontmatter', '// description: No delimiters.']),
    ];

    for (const fragment of invalidFragments) {
      expect(parseFragment(fragment)).toBeNull();
    }
  });
});

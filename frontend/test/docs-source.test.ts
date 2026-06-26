// @vitest-environment node
import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { handbookSource, productSource } from '@/lib/source';

/**
 * Recursively counts MDX / MD files under a directory, ignoring dotfiles.
 *
 * @param dir - directory to scan
 * @returns the count of `.md` and `.mdx` files
 */
async function countMdxFiles(dir: string): Promise<number> {
  const entries = await readdir(dir, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      count += await countMdxFiles(full);
    } else if (entry.name.endsWith('.mdx') || entry.name.endsWith('.md')) {
      count += 1;
    }
  }
  return count;
}

describe('Fumadocs loader parity', () => {
  it('handbook loader picks up every MDX file under content/docs/handbook/', async () => {
    const fileCount = await countMdxFiles(join(__dirname, '..', 'content', 'docs', 'handbook'));
    const loaderCount = handbookSource.getPages().length;
    expect(loaderCount).toBe(fileCount);
  });

  it('product loader picks up every MDX file under content/docs/product/', async () => {
    const fileCount = await countMdxFiles(join(__dirname, '..', 'content', 'docs', 'product'));
    const loaderCount = productSource.getPages().length;
    expect(loaderCount).toBe(fileCount);
  });
});

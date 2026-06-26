/**
 * Fumadocs MDX collection definitions.
 *
 * Two parallel collections (handbook, product) feed two distinct
 * loaders in `lib/source.ts`. Each collection has its own MDX
 * directory under `content/docs/`.
 */

import { defineConfig, defineDocs } from 'fumadocs-mdx/config';

/** Curated, public-safe internal handbook content. */
export const handbookDocs = defineDocs({
  dir: 'content/docs/handbook',
});

/** User-facing product documentation. */
export const productDocs = defineDocs({
  dir: 'content/docs/product',
});

export default defineConfig();

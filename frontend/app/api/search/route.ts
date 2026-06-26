/**
 * Fumadocs search endpoint: builds an Orama index at build time over
 * the handbook and product sources, served from the same Next deploy.
 * No external service.
 *
 * `createFromSource` accepts exactly one loader; to union the handbook
 * and product sources we fall through to `createSearchAPI` so both
 * collections feed a single Orama advanced index.
 */

import { createSearchAPI } from 'fumadocs-core/search/server';
import { handbookSource, productSource } from '@/lib/source';

/**
 * GET handler that returns the unified Orama search index for all docs.
 * Merges handbook and product pages into one searchable index.
 */
export const { GET } = createSearchAPI('advanced', {
  indexes: [
    ...handbookSource.getPages().map((page) => ({
      title: page.data.title as string,
      structuredData: page.data.structuredData,
      id: page.url,
      url: page.url,
    })),
    ...productSource.getPages().map((page) => ({
      title: page.data.title as string,
      structuredData: page.data.structuredData,
      id: page.url,
      url: page.url,
    })),
  ],
});

import { describe, expect, it } from 'vitest';
import { INTEGRATION_CATALOG, YOUR_INTEGRATIONS } from './catalog';

describe('integrations catalog', () => {
  it('starts empty until real integrations are implemented', () => {
    // Both lists are intentionally empty: no backend implementation
    // exists yet. Populate as real integrations land.
    expect(YOUR_INTEGRATIONS).toEqual([]);
    expect(INTEGRATION_CATALOG).toEqual([]);
  });

  it('keeps every catalog ID unique once populated', () => {
    const ids = INTEGRATION_CATALOG.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('mirrors YOUR_INTEGRATIONS into the catalog as installed entries', () => {
    // Invariant for the future: any "Your integrations" row must
    // also appear in the catalog with state='installed'.
    for (const integration of YOUR_INTEGRATIONS) {
      const catalogEntry = INTEGRATION_CATALOG.find((entry) => entry.id === integration.id);
      expect(catalogEntry).toBeDefined();
      expect(catalogEntry?.state).toBe('installed');
    }
  });
});

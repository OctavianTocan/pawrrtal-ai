import { describe, expect, it } from 'vitest';
import { SETTINGS_SECTION_IDS, SETTINGS_SECTIONS } from './constants';

describe('settings constants', () => {
  it('exposes a non-empty ordered section catalog', () => {
    expect(SETTINGS_SECTIONS.length).toBeGreaterThan(0);
    expect(SETTINGS_SECTIONS[0].id).toBe('general');
  });

  it('keeps every section ID matched against the SETTINGS_SECTION_IDS tuple', () => {
    const catalogIds = SETTINGS_SECTIONS.map((section) => section.id);
    expect(catalogIds).toEqual([...SETTINGS_SECTION_IDS]);
  });

  it('every section has a label and an icon', () => {
    for (const section of SETTINGS_SECTIONS) {
      expect(section.label).toBeTruthy();
      expect(section.Icon).toBeTypeOf('object');
    }
  });

  it('includes the integrations + usage sections', () => {
    const ids = SETTINGS_SECTIONS.map((section) => section.id);
    expect(ids).toContain('integrations');
    expect(ids).toContain('usage');
    expect(ids).toContain('personalization');
  });
});

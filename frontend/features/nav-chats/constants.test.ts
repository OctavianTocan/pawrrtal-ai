import { describe, expect, it } from 'vitest';
import { ARCHIVED_GROUP_KEY, getLabelById, NAV_CHATS_LABELS, NAV_CHATS_STORAGE_KEYS } from './constants';

describe('nav-chats constants', () => {
  it('exposes a stable archived group key with the underscore sentinel', () => {
    expect(ARCHIVED_GROUP_KEY).toBe('__archived__');
  });

  it('returns the matching label entry for a known ID', () => {
    const bug = getLabelById('bug');
    expect(bug?.name).toBe('Bug');
    expect(bug?.color).toMatch(/^#/);
  });

  it('returns undefined for an unknown label ID', () => {
    expect(getLabelById('not-a-label')).toBeUndefined();
  });

  it('keeps every label ID + color unique', () => {
    const ids = NAV_CHATS_LABELS.map((label) => label.id);
    const colors = NAV_CHATS_LABELS.map((label) => label.color);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(colors).size).toBe(colors.length);
  });

  it('keeps the collapsedGroups storage key stable', () => {
    expect(NAV_CHATS_STORAGE_KEYS.collapsedGroups).toBe('nav-chats-collapsed-groups');
  });
});

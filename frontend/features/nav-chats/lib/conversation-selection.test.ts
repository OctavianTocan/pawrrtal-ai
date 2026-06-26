import { describe, expect, it } from 'vitest';
import {
  clearMultiSelect,
  createInitialSelectionState,
  isMultiSelectActive,
  rangeSelect,
  singleSelect,
  toggleSelect,
} from './conversation-selection';

const items = ['a', 'b', 'c', 'd', 'e'];

describe('conversation-selection', () => {
  it('starts with nothing selected', () => {
    const s = createInitialSelectionState();
    expect(s.selected).toBeNull();
    expect(s.selectedIds.size).toBe(0);
    expect(isMultiSelectActive(s)).toBe(false);
  });

  it('singleSelect collapses everything to a single id and sets the anchor', () => {
    const s = singleSelect('b', 1);
    expect(s.selected).toBe('b');
    expect([...s.selectedIds]).toEqual(['b']);
    expect(s.anchorId).toBe('b');
    expect(s.anchorIndex).toBe(1);
  });

  it('toggleSelect adds new ids to the selection', () => {
    const s1 = singleSelect('b', 1);
    const s2 = toggleSelect(s1, 'd', 3);
    expect(s2.selectedIds.has('b')).toBe(true);
    expect(s2.selectedIds.has('d')).toBe(true);
    expect(isMultiSelectActive(s2)).toBe(true);
  });

  it('toggleSelect removes ids that are already selected (when more than one survives)', () => {
    let s = singleSelect('b', 1);
    s = toggleSelect(s, 'd', 3);
    s = toggleSelect(s, 'b', 1);
    expect(s.selectedIds.has('b')).toBe(false);
    expect(s.selectedIds.has('d')).toBe(true);
  });

  it('toggleSelect refuses to deselect the last remaining id', () => {
    const s = singleSelect('b', 1);
    const next = toggleSelect(s, 'b', 1);
    expect(next).toBe(s);
  });

  it('rangeSelect picks up everything between the anchor and the target', () => {
    const s = singleSelect('b', 1);
    const next = rangeSelect(s, 4, items);
    expect([...next.selectedIds].sort()).toEqual(['b', 'c', 'd', 'e']);
  });

  it('rangeSelect re-resolves the anchor by id when the cached index is stale', () => {
    const s = singleSelect('b', 1);
    const reordered = ['x', 'a', 'b', 'c', 'd'];
    const next = rangeSelect(s, 4, reordered);
    // b is now at index 2; range to 4 → [b, c, d]
    expect([...next.selectedIds].sort()).toEqual(['b', 'c', 'd']);
  });

  it('rangeSelect returns state unchanged when the items array is empty', () => {
    const s = singleSelect('b', 1);
    const next = rangeSelect(s, 0, []);
    expect(next).toBe(s);
  });

  it('clearMultiSelect collapses to the focused id', () => {
    let s = singleSelect('b', 1);
    s = toggleSelect(s, 'c', 2);
    const next = clearMultiSelect(s);
    expect(next.selectedIds.size).toBe(1);
  });

  it('clearMultiSelect resets to empty state when nothing is focused', () => {
    const empty = createInitialSelectionState();
    expect(clearMultiSelect(empty)).toEqual(empty);
  });

  it('isMultiSelectActive reports true only when 2+ ids are selected', () => {
    const s1 = singleSelect('a', 0);
    expect(isMultiSelectActive(s1)).toBe(false);
    const s2 = toggleSelect(s1, 'b', 1);
    expect(isMultiSelectActive(s2)).toBe(true);
  });
});

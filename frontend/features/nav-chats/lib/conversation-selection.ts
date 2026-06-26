/**
 * @file conversation-selection.ts
 *
 * Pure state machine for multi-select behavior in the sidebar conversation list.
 * Kept framework-agnostic (no React) so it can be unit-tested without rendering
 * and reused if the sidebar is ever ported to a different UI layer.
 *
 * The selection model mirrors native OS list selection:
 *   - Click: select one, deselect everything else.
 *   - Cmd/Ctrl+Click: toggle one item in/out of the selection.
 *   - Shift+Click: select a contiguous range from the anchor to the target.
 *
 * An "anchor" is the item where the last deliberate selection action started.
 * Range selects extend from the anchor to the new target. The anchor survives
 * list reordering because rangeSelect re-finds it by ID if the cached index
 * goes stale.
 */

/** Immutable snapshot of the current selection. */
export type MultiSelectState = {
  /** The "focused" or "primary" selected item (used for keyboard navigation). */
  selected: string | null;
  /** All currently selected item IDs. Size > 1 means multi-select is active. */
  selectedIds: Set<string>;
  /** The item that anchors shift+click range selections. */
  anchorId: string | null;
  /** Cached index of the anchor in the item list (may go stale after reorder). */
  anchorIndex: number;
};

/** Returns a blank selection state with nothing selected. */
export function createInitialSelectionState(): MultiSelectState {
  return {
    selected: null,
    selectedIds: new Set<string>(),
    anchorId: null,
    anchorIndex: -1,
  };
}

/**
 * Select exactly one item, clearing all others.
 * Sets the anchor so future shift+clicks extend from this point.
 */
export function singleSelect(id: string, index: number): MultiSelectState {
  return {
    selected: id,
    selectedIds: new Set([id]),
    anchorId: id,
    anchorIndex: index,
  };
}

/**
 * Toggle an item in or out of the selection (Cmd/Ctrl+Click).
 * Never allows the selection to drop to zero; if the user tries to
 * deselect the last remaining item, the state is returned unchanged.
 */
export function toggleSelect(state: MultiSelectState, id: string, index: number): MultiSelectState {
  const nextIds = new Set(state.selectedIds);

  if (nextIds.has(id)) {
    // Don't allow deselecting the last item — always keep at least one.
    if (nextIds.size <= 1) {
      return state;
    }

    nextIds.delete(id);
    return {
      selected: state.selected === id ? (nextIds.values().next().value ?? null) : state.selected,
      selectedIds: nextIds,
      anchorId: id,
      anchorIndex: index,
    };
  }

  nextIds.add(id);
  return {
    selected: id,
    selectedIds: nextIds,
    anchorId: id,
    anchorIndex: index,
  };
}

/**
 * Select a contiguous range from the anchor to the target index (Shift+Click).
 *
 * The anchor is resilient to reordering because we re-find it by `anchorId`
 * if the cached `anchorIndex` no longer matches. This prevents stale index
 * references from selecting the wrong range after the list is re-sorted.
 */
export function rangeSelect(state: MultiSelectState, toIndex: number, items: string[]): MultiSelectState {
  if (items.length === 0) {
    return state;
  }

  const clampedIndex = Math.max(0, Math.min(toIndex, items.length - 1));

  // Re-resolve the anchor by ID if the cached index is stale.
  let anchorIndex = clampedIndex;
  if (state.anchorIndex >= 0 && state.anchorIndex < items.length && items[state.anchorIndex] === state.anchorId) {
    anchorIndex = state.anchorIndex;
  } else if (state.anchorId) {
    const foundIndex = items.indexOf(state.anchorId);
    anchorIndex = foundIndex >= 0 ? foundIndex : clampedIndex;
  }

  const start = Math.min(anchorIndex, clampedIndex);
  const end = Math.max(anchorIndex, clampedIndex);
  const selectedIds = new Set<string>();

  for (let index = start; index <= end; index += 1) {
    const itemId = items[index];
    if (itemId) {
      selectedIds.add(itemId);
    }
  }

  const selectedId = items[clampedIndex] ?? state.selected;
  const anchorId = state.anchorId ?? items[anchorIndex] ?? selectedId;

  return {
    selected: selectedId,
    selectedIds,
    anchorId,
    anchorIndex,
  };
}

/**
 * Collapse multi-select back to a single selection on the currently focused item.
 * If nothing is focused, resets to the initial empty state entirely.
 */
export function clearMultiSelect(state: MultiSelectState): MultiSelectState {
  if (!state.selected) {
    return createInitialSelectionState();
  }

  return {
    selected: state.selected,
    selectedIds: new Set([state.selected]),
    anchorId: state.selected,
    anchorIndex: state.anchorIndex,
  };
}

/** True when more than one item is selected (batch operations should be available). */
export function isMultiSelectActive(state: MultiSelectState): boolean {
  return state.selectedIds.size > 1;
}

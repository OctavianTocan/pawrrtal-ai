/**
 * Sidebar conversation list behavior: search, multi-select, keyboard nav, and focus zones.
 *
 * @fileoverview Feeds {@link NavChatsView} with handlers derived from route, groups, and collapse state.
 */

'use client';

import { usePathname } from 'next/navigation';
import type {
  Dispatch,
  MutableRefObject,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  SetStateAction,
} from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ConversationGroup } from '@/lib/conversation-groups';
import { extractConversationIdFromPath } from '@/lib/route-utils';
import type { Conversation } from '@/lib/types';
import type { NavChatsViewProps } from '../components/NavChatsView';
import { useOptionalSidebarFocusContext } from '../context/sidebar-focus';
import type { MultiSelectState } from '../lib/conversation-selection';
import { createInitialSelectionState, rangeSelect, singleSelect, toggleSelect } from '../lib/conversation-selection';
import { useConversationSearch } from './use-conversation-search';

type OptionalSidebarFocus = ReturnType<typeof useOptionalSidebarFocusContext>;

/**
 * Parses a conversation id from a Next.js pathname like `/c/<id>`, or `null` if
 * the route is not a single-conversation view.
 */
function getConversationIdFromPathname(pathname: string | null): string | null {
  if (!pathname) {
    return null;
  }
  return extractConversationIdFromPath(pathname);
}

/**
 * Builds a flat, visible-order list of conversation ids from grouped data,
 * matching the list rendering rules in `NavChatsView` (collapse + search).
 */
function buildVisibleConversationIdOrder(
  isSearchActive: boolean,
  filteredGroups: ConversationGroup[],
  collapsedGroups: Set<string>
): string[] {
  const canCollapse = !isSearchActive && filteredGroups.length > 1;
  const collapsedKeys = canCollapse ? collapsedGroups : new Set<string>();
  const ids: string[] = [];

  for (const group of filteredGroups) {
    if (collapsedKeys.has(group.key)) {
      continue;
    }
    for (const conversation of group.items) {
      ids.push(conversation.id);
    }
  }

  return ids;
}

function usePathnameSelectionSync(
  pathConversationId: string | null,
  flatOrderIds: string[],
  setSelection: Dispatch<SetStateAction<MultiSelectState>>
): void {
  useEffect(() => {
    if (!pathConversationId) {
      setSelection(createInitialSelectionState());
      return;
    }

    const index = flatOrderIds.indexOf(pathConversationId);
    if (index >= 0) {
      setSelection(singleSelect(pathConversationId, index));
      return;
    }

    setSelection({
      selected: pathConversationId,
      selectedIds: new Set([pathConversationId]),
      anchorId: pathConversationId,
      anchorIndex: -1,
    });
  }, [pathConversationId, flatOrderIds, setSelection]);
}

/** Returns true if the event is a plain keypress (no Cmd/Ctrl/Alt held). */
function isPlainKeyPress(event: ReactKeyboardEvent): boolean {
  return !event.metaKey && !event.ctrlKey && !event.altKey;
}

/**
 * @returns Whether a Tab/Shift-Tab event was handled as a focus-zone escape.
 */
function tryHandleZoneEscape(event: ReactKeyboardEvent, focus: OptionalSidebarFocus): boolean {
  if (event.key !== 'Tab') return false;
  if (event.shiftKey) {
    focus?.focusPreviousZone();
  } else {
    focus?.focusNextZone();
  }
  event.preventDefault();
  return true;
}

/**
 * @returns Whether the keypress was an action shortcut (F2/E/Backspace) and
 *          was handled. Action shortcuts fire only on bare keys to avoid
 *          fighting with browser shortcuts like Cmd-E.
 */
function tryHandleActionShortcut(
  event: ReactKeyboardEvent,
  conversationId: string,
  handlers: {
    onRenameShortcut: (id: string) => void;
    onArchiveShortcut: (id: string) => void;
    onDeleteShortcut: (id: string) => void;
  }
): boolean {
  if (!isPlainKeyPress(event)) return false;
  if (event.key === 'F2') {
    event.preventDefault();
    handlers.onRenameShortcut(conversationId);
    return true;
  }
  if (event.key === 'e' || event.key === 'E') {
    event.preventDefault();
    handlers.onArchiveShortcut(conversationId);
    return true;
  }
  if (event.key === 'Backspace' || event.key === 'Delete') {
    event.preventDefault();
    handlers.onDeleteShortcut(conversationId);
    return true;
  }
  return false;
}

/** Resolves the next index for a roving keypress, or `null` if not applicable. */
function getNavTargetIndex(event: ReactKeyboardEvent, currentIndex: number, listLength: number): number | null {
  if (event.key === 'Home') return 0;
  if (event.key === 'End') return listLength - 1;
  if (event.key === 'ArrowUp') return currentIndex - 1;
  if (event.key === 'ArrowDown') return currentIndex + 1;
  return null;
}

/**
 * @returns Keyboard handler for roving list navigation, Tab zone escape,
 *          Home/End, and the F2 / E / Backspace action shortcuts.
 *
 * Internally split into small `tryHandle*` helpers so the cognitive
 * complexity of the dispatch loop stays under the project's lint budget.
 */
function createNavChatsListKeydownHandler(options: {
  flatOrderIds: string[];
  navigateTo: (href: string) => void;
  setSelection: Dispatch<SetStateAction<MultiSelectState>>;
  conversationElements: MutableRefObject<Map<string, HTMLDivElement>>;
  focus: OptionalSidebarFocus;
  onRenameShortcut: (conversationId: string) => void;
  onArchiveShortcut: (conversationId: string) => void;
  onDeleteShortcut: (conversationId: string) => void;
}): (event: ReactKeyboardEvent, conversation: Conversation, index: number) => void {
  const {
    flatOrderIds,
    navigateTo,
    setSelection,
    conversationElements,
    focus,
    onRenameShortcut,
    onArchiveShortcut,
    onDeleteShortcut,
  } = options;
  return (event, conversation, index) => {
    if (tryHandleZoneEscape(event, focus)) return;
    if (
      tryHandleActionShortcut(event, conversation.id, {
        onRenameShortcut,
        onArchiveShortcut,
        onDeleteShortcut,
      })
    ) {
      return;
    }

    const targetIndex = getNavTargetIndex(event, index, flatOrderIds.length);
    if (targetIndex === null || flatOrderIds.length === 0) return;
    event.preventDefault();

    const safeIndex = Math.max(0, Math.min(flatOrderIds.length - 1, targetIndex));
    const id = flatOrderIds[safeIndex];
    if (!id) return;
    setSelection(singleSelect(id, safeIndex));
    navigateTo(`/c/${id}`);
    const element = conversationElements.current.get(id);
    queueMicrotask(() => element?.focus());
  };
}

/**
 * Centralizes the sidebar list behavior required by `NavChatsView`: content
 * search, multi-select, keyboard navigation, and (optional) focus-zone hooks.
 */
export function useNavChatsOrchestration(input: {
  /** Raw conversation list; may be undefined while loading. */
  conversations: Conversation[] | undefined;
  /** Uncontrolled search input. */
  searchQuery: string;
  /** Grouped, filtered list passed to the view. */
  filteredGroups: ConversationGroup[];
  /** Collapse state for each date group. */
  collapsedGroups: Set<string>;
  /** Route navigation and mobile sidebar close (from `useConversationActions`). */
  navigateTo: (href: string) => void;
  /** Opens the rename modal for a conversation — fires on F2 from the keyboard. */
  onRenameShortcut: (conversationId: string) => void;
  /** Toggles archive on a conversation — fires on E from the keyboard. */
  onArchiveShortcut: (conversationId: string) => void;
  /** Opens the delete confirmation — fires on Backspace/Delete from the keyboard. */
  onDeleteShortcut: (conversationId: string) => void;
}): Pick<
  NavChatsViewProps,
  | 'navigatorRef'
  | 'contentSearchResults'
  | 'activeChatMatchInfo'
  | 'multiSelectedIds'
  | 'focusedConversationId'
  | 'onConversationClick'
  | 'onConversationMouseDown'
  | 'onConversationKeyDown'
  | 'registerConversationElement'
  | 'onNavigatorMouseDown'
  | 'isSearchActive'
> {
  const {
    conversations,
    searchQuery,
    filteredGroups,
    collapsedGroups,
    navigateTo,
    onRenameShortcut,
    onArchiveShortcut,
    onDeleteShortcut,
  } = input;
  const conversationList = conversations ?? [];
  const pathname = usePathname();
  const pathConversationId = getConversationIdFromPathname(pathname);
  const sidebarFocus = useOptionalSidebarFocusContext();

  const { contentSearchResults, activeChatMatchInfo, isSearchActive } = useConversationSearch({
    conversations: conversationList,
    searchQuery,
    activeConversationId: pathConversationId,
  });

  const flatOrderIds = useMemo(
    () => buildVisibleConversationIdOrder(isSearchActive, filteredGroups, collapsedGroups),
    [isSearchActive, filteredGroups, collapsedGroups]
  );

  const [selection, setSelection] = useState<MultiSelectState>(createInitialSelectionState);
  const navigatorRef = useRef<HTMLDivElement | null>(null);
  const conversationElements = useRef(new Map<string, HTMLDivElement>());
  const pendingModifier = useRef<'none' | 'meta' | 'shift'>('none');

  usePathnameSelectionSync(pathConversationId, flatOrderIds, setSelection);

  const onNavigatorMouseDown = useCallback((): void => {
    sidebarFocus?.focusZone('navigator', { intent: 'click' });
  }, [sidebarFocus]);

  const registerConversationElement = useCallback((conversationId: string, element: HTMLDivElement | null): void => {
    if (element) {
      conversationElements.current.set(conversationId, element);
    } else {
      conversationElements.current.delete(conversationId);
    }
  }, []);

  const onConversationMouseDown = useCallback(
    (event: ReactMouseEvent, conversationId: string, index: number): void => {
      onNavigatorMouseDown();
      if (event.shiftKey) {
        setSelection((current) => rangeSelect(current, index, flatOrderIds));
        pendingModifier.current = 'shift';
        return;
      }

      if (event.metaKey || event.ctrlKey) {
        setSelection((current) => toggleSelect(current, conversationId, index));
        pendingModifier.current = 'meta';
        return;
      }

      pendingModifier.current = 'none';
    },
    [flatOrderIds, onNavigatorMouseDown]
  );

  const onConversationClick = useCallback(
    (conversationId: string, index: number, href: string): void => {
      const modifier = pendingModifier.current;
      pendingModifier.current = 'none';
      // Cmd/Ctrl-click and Shift-click are pure multi-select gestures —
      // neither one navigates. Navigating on Shift-click previously
      // caused the URL to change, which fired `usePathnameSelectionSync`
      // and collapsed the freshly-extended range back to a single row
      // (the deselect-after-shift-click bug). Match Finder/Linear: the
      // modifier extends the selection, plain click is the only thing
      // that changes the active conversation.
      if (modifier === 'meta' || modifier === 'shift') {
        return;
      }
      setSelection(singleSelect(conversationId, index));
      navigateTo(href);
    },
    [navigateTo]
  );

  const onConversationKeyDown = useMemo(
    () =>
      createNavChatsListKeydownHandler({
        flatOrderIds,
        navigateTo,
        setSelection,
        conversationElements,
        focus: sidebarFocus,
        onRenameShortcut,
        onArchiveShortcut,
        onDeleteShortcut,
      }),
    [flatOrderIds, navigateTo, sidebarFocus, onRenameShortcut, onArchiveShortcut, onDeleteShortcut]
  );

  return {
    navigatorRef,
    contentSearchResults,
    activeChatMatchInfo,
    multiSelectedIds: selection.selectedIds,
    focusedConversationId: selection.selected,
    onConversationClick,
    onConversationMouseDown,
    onConversationKeyDown,
    registerConversationElement,
    onNavigatorMouseDown,
    isSearchActive,
  };
}

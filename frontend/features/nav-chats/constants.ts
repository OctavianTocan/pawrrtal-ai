/**
 * Centralized constants for the nav-chats feature.
 *
 * Mirrors the pattern established by `features/chat/constants.ts`: a single
 * keys object for everything we persist to `localStorage`, plus any defaults
 * that more than one file in the feature would otherwise inline.
 */

// ─── localStorage keys ─────────────────────────────────────────────────────

/**
 * Single source of truth for every `localStorage` key the nav-chats feature
 * owns. Existing key strings are intentionally preserved verbatim — renaming
 * them would orphan every user's collapsed-group preferences.
 */
export const NAV_CHATS_STORAGE_KEYS = {
  /** Set of date-group keys the user has manually collapsed in the sidebar list. */
  collapsedGroups: 'nav-chats-collapsed-groups',
} as const;

/** Union of every recognized nav-chats `localStorage` key. */
export type NavChatsStorageKey = (typeof NAV_CHATS_STORAGE_KEYS)[keyof typeof NAV_CHATS_STORAGE_KEYS];

/**
 * Stable group key for the Archived bucket rendered at the bottom of the
 * sidebar. Lives in the same collapse-state set as the date groups so the
 * existing persistence logic Just Works™. The leading double-underscore
 * keeps it unambiguous against any future date label that could collide.
 */
export const ARCHIVED_GROUP_KEY = '__archived__';

// ─── Pre-defined labels (L1) ───────────────────────────────────────────────

/**
 * Pre-defined label catalog (decision L1: pre-defined set, no user CRUD).
 *
 * Order here is the order rendered in the labels submenu — declared as a
 * tuple so the inferred union types stay narrow. Colors are CSS custom
 * properties (theme-aware) when available, otherwise hex.
 *
 * To add a label: append a row, ship a frontend deploy. No backend
 * migration is required because labels are stored as raw IDs in the
 * conversation row's JSON `labels` array.
 */
export const NAV_CHATS_LABELS = [
  { id: 'bug', name: 'Bug', color: '#ef4444' },
  { id: 'feature', name: 'Feature', color: '#3b82f6' },
  { id: 'idea', name: 'Idea', color: '#a855f7' },
  { id: 'question', name: 'Question', color: '#eab308' },
  { id: 'reference', name: 'Reference', color: '#10b981' },
  // Auto-applied by the backend when the user's heartbeat
  // conversation is lazy-created on first `/api/v1/heartbeat/sync`.
  // The row is undeletable server-side; pinning above the date
  // groups in the sidebar is a frontend follow-up.
  { id: 'heartbeat', name: 'Heartbeat', color: '#ec4899' },
] as const satisfies ReadonlyArray<{ id: string; name: string; color: string }>;

/** Union of every pre-defined label ID. Use as the storage shape on conversations. */
export type NavChatsLabelId = (typeof NAV_CHATS_LABELS)[number]['id'];

/** Look up a label's display metadata by ID, returning undefined for unknown IDs. */
export function getLabelById(id: string): (typeof NAV_CHATS_LABELS)[number] | undefined {
  return NAV_CHATS_LABELS.find((label) => label.id === id);
}

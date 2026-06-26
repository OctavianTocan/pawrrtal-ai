/**
 * Tasks feature constants.
 *
 * View identifiers, priority enum, project tones, URL parameter keys, and
 * `localStorage` keys live here so the container, view, sub-sidebar, and
 * any future deep-linker share a single source of truth. `as const`
 * preserves literal types for derived unions in `./types.ts`.
 */

/**
 * All sub-views of the Tasks surface.
 *
 * Order in this object matters — the sub-sidebar groups them in the order
 * declared (Lists group: today / upcoming / inbox, Projects group: each
 * project as its own row).
 */
export const TASK_VIEWS = {
  today: 'today',
  upcoming: 'upcoming',
  inbox: 'inbox',
  completed: 'completed',
} as const;

/** Default sub-view when `?view=` is absent or unrecognised. */
export const DEFAULT_TASK_VIEW = TASK_VIEWS.today;

/** Keys used on the `/tasks` route to encode the current view + filter. */
export const TASK_QUERY_KEYS = {
  view: 'view',
  filter: 'filter',
} as const;

/**
 * Priority buckets in descending urgency. The order matters — section
 * sorts use the index as the urgency weight (lower index = more urgent).
 */
export const TASK_PRIORITIES = ['urgent', 'high', 'normal', 'low'] as const;

/**
 * Tint vocabulary for project chips. Each token resolves to a class string
 * inside the chip component; we keep the union narrow so drift across
 * projects stays impossible.
 */
export const TASK_PROJECT_TONES = ['neutral', 'info', 'success', 'accent', 'destructive'] as const;

/**
 * Tailwind class strings for the priority ring on each task row's
 * checkbox. Keyed by priority so the row component never inlines a switch.
 *
 * Uses `ring-inset` so the ring lands inside the checkbox's hit area
 * without expanding the cell — preserving optical alignment with the
 * task title's cap-height.
 */
export const PRIORITY_RING: Record<(typeof TASK_PRIORITIES)[number], string> = {
  urgent: 'ring-2 ring-inset ring-destructive/60',
  high: 'ring-2 ring-inset ring-info/60',
  normal: 'ring-[1.5px] ring-inset ring-foreground/25',
  low: 'ring-[1.5px] ring-inset ring-foreground/12',
};

/**
 * Tailwind class strings for project chip backgrounds and text colors.
 * Keyed by tone so the chip component never inlines a switch.
 */
export const PROJECT_TONE_CLASSES: Record<(typeof TASK_PROJECT_TONES)[number], string> = {
  neutral: 'bg-foreground/[0.05] text-muted-foreground',
  info: 'bg-info/10 text-info-text',
  success: 'bg-success/10 text-success-text',
  accent: 'bg-accent/10 text-accent',
  destructive: 'bg-destructive/10 text-destructive-text',
};

/**
 * `localStorage` keys owned by the Tasks feature. Namespaced with `tasks:`
 * so they don't collide with sidebar / chat / nav keys in the same origin.
 *
 * Keep this object as the single source of truth — no inline string
 * literals when reading or writing storage from feature code.
 */
export const TASK_STORAGE_KEYS = {
  /** Set of section IDs the user has collapsed in the current view. */
  collapsedSections: 'tasks:collapsed-sections',
  /** Set of task IDs the user has marked complete locally (mock only). */
  completedTaskIds: 'tasks:completed-task-ids',
} as const;

/**
 * Maximum length of a task title before the row truncates with ellipsis.
 * 96 characters preserves the editorial feel without letting a single row
 * dominate the list height.
 */
const _TASK_TITLE_MAX_LENGTH = 96;

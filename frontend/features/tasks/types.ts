/**
 * Type definitions for the Tasks feature.
 *
 * The Tasks surface is a multi-view editorial todo list inspired by Todoist,
 * translated into the Pawrrtal warm-cream visual language. All shapes here
 * describe in-memory mock data — there is no backend integration yet. Once
 * a real source materialises, these types stay as-is and only the data
 * fetcher swaps.
 */

import type { TASK_PRIORITIES, TASK_PROJECT_TONES, TASK_VIEWS } from './constants';

/**
 * The active sub-view inside the Tasks surface.
 *
 * Drives the content of both the inner sub-sidebar (which row is highlighted)
 * and the right-hand pane (which surface renders). Mirrored to the URL via
 * `?view=...` so reloading or sharing a URL restores the same view.
 */
export type TaskViewId = (typeof TASK_VIEWS)[keyof typeof TASK_VIEWS];

/**
 * Priority bucket for a task — controls the checkbox ring tint and its
 * sort weight inside an unsorted section.
 *
 * `urgent` paints destructive, `high` paints info, `normal` and `low` use
 * progressively lighter foreground mixes so untriaged items recede.
 */
export type TaskPriority = (typeof TASK_PRIORITIES)[number];

/**
 * Tinted background palette for a project chip. Mirrors the limited tint
 * vocabulary in DESIGN.md — we deliberately reuse `info`/`success`/`accent`
 * tokens with low alpha rather than introducing literal colors.
 */
export type TaskProjectTone = (typeof TASK_PROJECT_TONES)[number];

/**
 * One project the user can file tasks under.
 *
 * Projects show as right-aligned chips on each task row and as nav entries
 * inside the sub-sidebar. `tone` is the only visual variable the chip
 * accepts so projects render consistently across the surface.
 */
export interface TaskProject {
  /** Stable identifier — used as the React key, the URL slug, and the chip key. */
  id: string;
  /** Display label rendered in the chip and the sub-sidebar row. */
  name: string;
  /** Optional emoji glyph rendered to the left of the chip label. Survival-mode badges use this. */
  emoji?: string;
  /** Tint mapping for the chip's background and text color. */
  tone: TaskProjectTone;
}

/**
 * One task in the mock list.
 *
 * `dueAt` is `null` for tasks without a due date (Inbox-style staging).
 * `flags` is open-ended so future markers (`pinned`, `recurring`) can land
 * without breaking existing rows.
 */
export interface Task {
  /** Stable identifier — used as the React key and any future routing slug. */
  id: string;
  /** One-line title shown in the row's primary text slot. */
  title: string;
  /** Optional one-line description rendered under the title (clamped to one line). */
  description?: string;
  /** Due moment — `null` means "no due date" (only valid in the Inbox view). */
  dueAt: Date | null;
  /** Mock completion state — toggled locally, never persisted. */
  completed: boolean;
  /** Priority bucket controlling checkbox ring and section sort weight. */
  priority: TaskPriority;
  /** Foreign key to {@link TaskProject.id}. */
  projectId: string;
  /** Lower-cased tag list rendered as `#tag` chips in the metadata strip. */
  tags: readonly string[];
  /** Optional flag set — the only currently-supported value is `survival-mode`. */
  flags?: readonly TaskFlag[];
}

/**
 * Flags marking secondary visual treatment on a task row. Today only
 * `survival-mode` exists, which paints the project chip with a fire emoji
 * and a destructive-tinted background regardless of the project's own tone.
 */
export type TaskFlag = 'survival-mode' | 'flagged';

/**
 * A grouped section in the rendered task list (e.g. Overdue, Today).
 *
 * Sections own their own collapsed state inside the view (persisted in
 * `localStorage`). The container computes which section a task lands in
 * from its `dueAt` relative to "now"; the view never re-bins.
 */
export interface TaskSectionData {
  /** Stable section key used for collapse persistence and React keys. */
  id: string;
  /** Heading label rendered in the section header (e.g. `Overdue`, `Today`). */
  label: string;
  /** Optional subtitle to the right of the heading (e.g. `Mon 5 May`). */
  subtitle?: string;
  /** Tasks belonging to this section, already sorted in display order. */
  tasks: readonly Task[];
  /**
   * When set, the section header renders this affordance to the right of
   * the title (e.g. an Overdue section showing a "Reschedule" link).
   */
  rightAction?: {
    label: string;
    onClick: () => void;
  };
  /**
   * Optional tone for the section header text. Defaults to neutral — only
   * Overdue uses `destructive` so the urgency reads at a glance.
   */
  tone?: 'neutral' | 'destructive';
}

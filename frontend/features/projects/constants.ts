/**
 * Constants for the projects feature.
 *
 * The conversation drag MIME used to live here too, but it's consumed by
 * both `features/nav-chats/` (drag source) and `features/projects/` (drop
 * target). It now lives at `@/lib/conversations/drag` to avoid a
 * cross-feature edge.
 */

/** localStorage keys owned by the projects feature. */
export const PROJECTS_STORAGE_KEYS = {
  /** Set of project IDs the user has manually collapsed in the sidebar. */
  collapsedProjects: 'projects:collapsed',
} as const;

/** Union of every recognized projects `localStorage` key. */
export type ProjectsStorageKey = (typeof PROJECTS_STORAGE_KEYS)[keyof typeof PROJECTS_STORAGE_KEYS];

/**
 * Knowledge feature constants.
 *
 * View identifiers and URL parameter keys live here so the container, view,
 * sub-sidebar, and any future deep-linker share a single source of truth.
 * `as const` preserves literal types for derived unions in `./types.ts`.
 */

/**
 * All sub-views of the Knowledge surface.
 *
 * Order in this object matters — the sub-sidebar groups them in the order
 * declared (Workspace group: my-files / memory / skills, Shared group:
 * brain-access / shared-with-me / shared-by-me).
 */
export const KNOWLEDGE_VIEWS = {
  myFiles: 'my-files',
  memory: 'memory',
  skills: 'skills',
  brainAccess: 'brain-access',
  sharedWithMe: 'shared-with-me',
  sharedByMe: 'shared-by-me',
} as const;

/** Keys used on the `/knowledge` route to encode the current view + path. */
export const KNOWLEDGE_QUERY_KEYS = {
  view: 'view',
  path: 'path',
} as const;

/** Default sub-view when `?view=` is absent or unrecognised. */
export const DEFAULT_KNOWLEDGE_VIEW = KNOWLEDGE_VIEWS.myFiles;

/**
 * Path separator used in `?path=` query strings.
 *
 * Forward slashes match the visual breadcrumb (`My Files / Misc / Daily Briefs`)
 * and are URL-encoded by the framework when written to the address bar.
 */
export const KNOWLEDGE_PATH_SEPARATOR = '/';

/** Suffix that switches the right pane into the document viewer. */
export const KNOWLEDGE_FILE_EXTENSION = '.md';

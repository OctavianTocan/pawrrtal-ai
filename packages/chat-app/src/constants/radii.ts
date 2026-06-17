/**
 * Corner-radius scale (in px).
 *
 * The brand spec uses a single 4px corner radius across the interface, so the
 * named steps all resolve to 4 — the scale is kept as distinct tokens so call
 * sites stay semantic and a future change to one role doesn't touch them all.
 * `full` stays large for genuinely circular controls (avatars, icon buttons).
 */
export const radii = {
  sm: 4,
  md: 4,
  lg: 4,
  xl: 4,
  /** Large popovers / composer surface. */
  xxl: 4,
  /** Pills and circular controls. */
  full: 9999,
} as const;

/** Union of valid radius token names. */
export type RadiusToken = keyof typeof radii;

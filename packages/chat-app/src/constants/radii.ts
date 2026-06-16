/** Corner-radius scale (in px). */
export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  /** Pills and circular controls. */
  full: 9999,
} as const;

/** Union of valid radius token names. */
export type RadiusToken = keyof typeof radii;

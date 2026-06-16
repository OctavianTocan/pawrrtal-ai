/** Spacing scale (in px) used for padding, margins, and gaps. */
export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

/** Union of valid spacing token names. */
export type SpacingToken = keyof typeof spacing;

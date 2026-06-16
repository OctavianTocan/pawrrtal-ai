/**
 * Motion tokens — durations and spring presets for Reanimated transitions
 * (popover open/close, drawer slide, voice-capture sweep).
 */
export const duration = {
  fast: 140,
  base: 220,
  slow: 320,
} as const;

/** Reanimated spring config for popover / sheet entrances. */
export const spring = {
  damping: 22,
  stiffness: 240,
  mass: 0.7,
} as const;

/** Union of valid duration token names. */
export type DurationToken = keyof typeof duration;

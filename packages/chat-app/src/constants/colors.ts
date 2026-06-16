/**
 * Color tokens for the chat app DARK theme.
 *
 * Sampled to match the reference chat UI: a near-black canvas, lifted dark
 * surfaces for the input bar / popovers / menu rows, white body text, muted
 * grey secondary text, and a white "primary action" pill whose foreground
 * flips to black. All UI colors must reference these tokens — never inline a
 * literal hex in a component (Biome's `noReactNativeLiteralColors` enforces it).
 */
export const colors = {
  /** App canvas — near-black (sampled from the reference home canvas). */
  background: '#0E0E10',
  /** Input bar / card / popover surface — lifted off black (≈ composer bar). */
  surface: '#1C1C1E',
  /** Menu rows, selected popover row, raised chips. */
  surfaceElevated: '#2C2C2E',
  /** Selected/active row inside an elevated surface — a touch LIGHTER than it. */
  rowSelected: '#3A3A3C',
  /** Suggestion chips / secondary buttons on the canvas. */
  surfaceMuted: '#161618',
  /** Hairline dividers and input/border outlines. */
  border: '#2A2A2C',

  /** Primary (body) text — white. */
  textPrimary: '#FFFFFF',
  /** Secondary text — muted grey subtitles, timestamps, placeholders. */
  textSecondary: '#98989D',
  /** Tertiary text — faint captions and disabled glyphs. */
  textTertiary: '#636366',

  /** Primary-action pill fill (the "Speak"/send button) — white. */
  accent: '#FFFFFF',
  /** Foreground placed ON the white accent fill — stays black for contrast. */
  onAccent: '#000000',

  /** Centered logo watermark on the empty home canvas. */
  watermark: '#2C2C30',

  /** Destructive actions (Sign out). */
  danger: '#FF453A',

  /** Voice-capture waveform gradient (teal sweep). */
  voiceStart: '#0B3B3B',
  voiceMid: '#0E7C7C',
  voiceEnd: '#14B8A6',

  /** Live "recording" status dot. */
  recording: '#34C759',

  /** Fully transparent — for layered scrims. */
  transparent: 'transparent',
} as const;

/** Union of valid color token names. */
export type ColorToken = keyof typeof colors;

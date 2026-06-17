/**
 * Color tokens for the chat app LIGHT theme.
 *
 * New brand identity (replaces the Grok dark clone): a white canvas, soft-blue
 * elevated surfaces, dark grey body text, a blue primary action, and hairline
 * borders drawn in 10%-opacity black. All UI colors must reference these
 * tokens — never inline a literal hex in a component (Biome's
 * `noReactNativeLiteralColors` enforces it).
 */
export const colors = {
  /** App canvas — white. */
  background: '#FFFFFF',
  /** Input bar / card / popover surface — white, separated by the 10% border. */
  surface: '#FFFFFF',
  /** Menu rows, raised chips, popover rows — soft blue. */
  surfaceElevated: '#F0F6FE',
  /** Selected/active row inside an elevated surface — a touch deeper blue. */
  rowSelected: '#E1ECF9',
  /** Suggestion chips / secondary buttons on the canvas — soft blue. */
  surfaceMuted: '#F0F6FE',
  /** Hairline dividers and input/border outlines — black at 10% opacity. */
  border: 'rgba(0, 0, 0, 0.1)',

  /** Primary (body) text — dark grey. */
  textPrimary: '#383838',
  /** Secondary text — muted subtitles, timestamps, placeholders. */
  textSecondary: 'rgba(56, 56, 56, 0.6)',
  /** Tertiary text — faint captions and disabled glyphs. */
  textTertiary: 'rgba(56, 56, 56, 0.4)',

  /** Primary-action fill (the "Speak"/send button) — brand blue. */
  accent: '#447AAC',
  /** Foreground placed ON the blue accent fill — white for contrast. */
  onAccent: '#FFFFFF',

  /** Centered logo watermark on the empty home canvas — faint blue. */
  watermark: '#E1ECF9',

  /** Destructive actions (Sign out). */
  danger: '#E5484D',

  /** Voice-capture pill tint — a subtle soft-blue sweep. */
  voiceStart: '#F0F6FE',
  voiceMid: '#EAF2FC',
  voiceEnd: '#F0F6FE',

  /** Live "recording" status dot. */
  recording: '#34C759',

  /** Fully transparent — for layered scrims. */
  transparent: 'transparent',
} as const;

/** Union of valid color token names. */
export type ColorToken = keyof typeof colors;

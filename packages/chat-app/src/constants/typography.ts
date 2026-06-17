/**
 * `TextStyle` presets for the chat app type scale.
 *
 * Brand fonts: ABC Diatype (primary interface sans), Lora (serif display),
 * DM Mono (metadata / labels), at a 14px base with 0 letter-spacing.
 *
 * WHY the sans role is Inter: ABC Diatype is a commercial Dinamo typeface that
 * is not distributable via npm, so it cannot be bundled here. Until its font
 * files are dropped into `assets/fonts/` and registered, the interface sans
 * role is backed by Inter — the closest free grotesque. Swap the four
 * `sans*` PostScript names below for the Diatype faces once available; nothing
 * else needs to change. Lora and DM Mono are loaded via @expo-google-fonts in
 * the root layout.
 */
import type { TextStyle } from 'react-native';

/** Font family constants (loaded via expo-font in the root layout). */
export const fontFamily = {
  /** Interface sans (ABC Diatype slot — Inter fallback until the file lands). */
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semiBold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  /** Serif display (Lora) — screen titles and the home tab labels. */
  serifSemiBold: 'Lora_600SemiBold',
  serifBold: 'Lora_700Bold',
  /** Monospace (DM Mono) — section labels, timestamps, metadata. */
  mono: 'DMMono_400Regular',
  monoMedium: 'DMMono_500Medium',
} as const;

/**
 * Upper bound on OS Dynamic Type growth applied to themed text.
 *
 * WHY: the chat surfaces (tab labels, model pill, menu rows) are dense; letting
 * the system font scale grow unbounded overflows those fixed-height boxes.
 */
export const MAX_FONT_SIZE_MULTIPLIER = 1.4;

/**
 * Typography presets mapping variant names to `TextStyle` objects.
 *
 * Most interface text sits at 14px with 0 letter-spacing per the brand spec.
 */
export const typography = {
  /** Tab labels in the header ("Ask" / "Imagine") — serif display. */
  titleLarge: { fontFamily: fontFamily.serifBold, fontSize: 20, lineHeight: 26, letterSpacing: 0 },
  /** Screen titles ("Settings"), drawer account name — serif. */
  title: { fontFamily: fontFamily.serifSemiBold, fontSize: 17, lineHeight: 22, letterSpacing: 0 },
  /** Row titles in menus, conversation titles, model names. */
  bodyStrong: { fontFamily: fontFamily.semiBold, fontSize: 14, lineHeight: 19, letterSpacing: 0 },
  /** Default body, composer text. */
  body: { fontFamily: fontFamily.regular, fontSize: 14, lineHeight: 20, letterSpacing: 0 },
  /** Button / pill labels. */
  label: { fontFamily: fontFamily.medium, fontSize: 14, lineHeight: 18, letterSpacing: 0 },
  /** Subtitles / timestamps — monospace. */
  caption: { fontFamily: fontFamily.mono, fontSize: 12, lineHeight: 16, letterSpacing: 0 },
  /** Section headers ("Grok", "Voice") — monospace. */
  overline: { fontFamily: fontFamily.monoMedium, fontSize: 12, lineHeight: 15, letterSpacing: 0 },
} as const satisfies Record<string, TextStyle>;

/** Union of valid typography variant names. */
export type TypographyVariant = keyof typeof typography;

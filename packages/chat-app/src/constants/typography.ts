/**
 * Inter-backed `TextStyle` presets for the chat app type scale.
 *
 * WHY: `expo-font` registers PostScript names; this file is the single place
 * that maps role names → those families and the role → size/line-height scale.
 * Inter is loaded via expo-font in the root layout.
 */
import type { TextStyle } from 'react-native';

/** Font family constants (Inter weights loaded via @expo-google-fonts/inter). */
export const fontFamily = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semiBold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
} as const;

/**
 * Upper bound on OS Dynamic Type growth applied to themed text.
 *
 * WHY: the chat surfaces (tab labels, model pill, menu rows) are dense; letting
 * the system font scale grow unbounded overflows those fixed-height boxes.
 */
export const MAX_FONT_SIZE_MULTIPLIER = 1.4;

/** Typography presets mapping variant names to `TextStyle` objects. */
export const typography = {
  /** Tab labels in the header ("Ask" / "Imagine"). */
  titleLarge: { fontFamily: fontFamily.bold, fontSize: 18, lineHeight: 24 },
  /** Screen titles ("Settings"), drawer account name. */
  title: { fontFamily: fontFamily.bold, fontSize: 17, lineHeight: 22 },
  /** Row titles in menus, conversation titles, model names. */
  bodyStrong: { fontFamily: fontFamily.semiBold, fontSize: 15, lineHeight: 20 },
  /** Default body, composer text. */
  body: { fontFamily: fontFamily.regular, fontSize: 15, lineHeight: 21 },
  /** Button / pill labels. */
  label: { fontFamily: fontFamily.semiBold, fontSize: 14, lineHeight: 18 },
  /** Subtitles ("Powered by ...", timestamps). */
  caption: { fontFamily: fontFamily.regular, fontSize: 12.5, lineHeight: 16 },
  /** Section headers ("App", "Conversations"). */
  overline: { fontFamily: fontFamily.medium, fontSize: 12, lineHeight: 15 },
} as const satisfies Record<string, TextStyle>;

/** Union of valid typography variant names. */
export type TypographyVariant = keyof typeof typography;

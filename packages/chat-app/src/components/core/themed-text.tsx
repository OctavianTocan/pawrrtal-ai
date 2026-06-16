/**
 * `ThemedText` — the design-system text primitive. Use this instead of a raw
 * `<Text>` so every label shares the typography and color tokens. (Biome's
 * `noReactNativeRawText` rule skips this component name.)
 */
import { StyleSheet, Text, type TextProps } from 'react-native';
import { type ColorToken, colors } from '@/constants/colors';
import {
  MAX_FONT_SIZE_MULTIPLIER,
  type TypographyVariant,
  typography,
} from '@/constants/typography';

/** Props for {@link ThemedText}. */
export type ThemedTextProps = TextProps & {
  /** Typography preset variant. */
  variant?: TypographyVariant;
  /** Color token name. */
  color?: ColorToken;
  /** Center the text. */
  centered?: boolean;
};

/** Themed text component bound to the design tokens. */
export function ThemedText({
  variant = 'body',
  color = 'textPrimary',
  centered = false,
  style,
  maxFontSizeMultiplier = MAX_FONT_SIZE_MULTIPLIER,
  children,
  ...rest
}: ThemedTextProps): React.JSX.Element {
  return (
    <Text
      maxFontSizeMultiplier={maxFontSizeMultiplier}
      style={[typography[variant], { color: colors[color] }, centered && styles.centered, style]}
      {...rest}
    >
      {children}
    </Text>
  );
}

const styles = StyleSheet.create({
  centered: { textAlign: 'center' },
});

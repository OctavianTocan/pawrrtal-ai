/**
 * Ambient types for Hugeicons deep per-icon imports.
 *
 * `@hugeicons/core-free-icons` ships type declarations only for its barrel
 * entry, not for the individual `./<Name>Icon` subpath modules we deep-import
 * (to keep Metro from crawling all ~11k icons). Each per-icon module default-
 * exports an `IconSvgElement`, so declare that shape for the subpath here.
 */
declare module '@hugeicons/core-free-icons/*' {
  import type { IconSvgElement } from '@hugeicons/react-native';

  const icon: IconSvgElement;
  export default icon;
}

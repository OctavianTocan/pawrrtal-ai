/**
 * `AccountAvatar` — the signed-in user's profile photo, shown in the
 * conversations drawer header and the settings account card. The image asset
 * lives in `assets/avatar.png`; the component clips it to a circle at the
 * requested size.
 */
import { Image, StyleSheet } from 'react-native';

/** The bundled account avatar photo. */
const AVATAR_SOURCE = require('../../../assets/avatar.png');

/** Props for {@link AccountAvatar}. */
export interface AccountAvatarProps {
  /** Square diameter in px; the image is clipped to a circle of this size. */
  size: number;
}

/** Render the account avatar photo clipped to a circle. */
export function AccountAvatar({ size }: AccountAvatarProps): React.JSX.Element {
  return (
    <Image
      accessibilityLabel="Account avatar"
      source={AVATAR_SOURCE}
      style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}
    />
  );
}

const styles = StyleSheet.create({
  avatar: { resizeMode: 'cover' },
});

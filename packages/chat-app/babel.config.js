/**
 * Expo / Metro Babel preset entry.
 *
 * WHY: Reanimated 4 splits its worklet transform into `react-native-worklets`.
 * The plugin rewrites worklet / `useAnimatedStyle` callbacks so they run on the
 * UI thread; it MUST be the LAST plugin so it processes the fully-transformed tree.
 */
module.exports = (api) => {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-worklets/plugin'],
  };
};

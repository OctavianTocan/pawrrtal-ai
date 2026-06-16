// Learn more https://docs.expo.dev/guides/customizing-metro
const { getDefaultConfig } = require('expo/metro-config');

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

// ── Effect v4 ESM / package-exports resolution ────────────────────────
//
// Effect v4 ships a unified package whose subpaths (`effect/unstable/*`,
// schema, etc.) are resolved through the `package.json` `exports` map.
// Metro only honours those maps when `unstable_enablePackageExports` is on,
// otherwise the v4 subpath imports fail to resolve under Hermes/Metro.
config.resolver.unstable_enablePackageExports = true;

module.exports = config;

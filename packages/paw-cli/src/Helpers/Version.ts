import packageManifest from '../../package.json' with { type: 'json' };

/** CLI package version shared by version output and health checks. */
export const CLI_VERSION = packageManifest.version;

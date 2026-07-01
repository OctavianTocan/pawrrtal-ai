import { Effect, Schema } from 'effect';
import packageManifest from '../../package.json' with { type: 'json' };
import { ConfigError } from './Errors';

export const PackageManifestSummarySchema = Schema.Struct({
  version: Schema.NonEmptyString,
}).pipe(
  Schema.annotate({
    identifier: 'PackageManifestSummary',
    title: 'Package Manifest Summary',
    description: 'Package metadata required by the Paw CLI runtime.',
  })
);

export type PackageManifestSummary = typeof PackageManifestSummarySchema.Type;

/** CLI package version shared by version output and health checks. */
export const CLI_VERSION = decodePackageManifestSummarySync(packageManifest).version;

/**
 * Decodes package metadata needed by the CLI.
 *
 * @param manifest - Package manifest object.
 * @param source - Source label for diagnostics.
 * @returns Package manifest summary.
 */
export function decodePackageManifestSummary(
  manifest: object,
  source = 'packages/paw-cli/package.json'
): Effect.Effect<PackageManifestSummary, ConfigError> {
  return Schema.decodeUnknownEffect(PackageManifestSummarySchema)(manifest).pipe(
    Effect.mapError(
      (schemaError) =>
        new ConfigError({
          message: `Could not decode CLI package metadata from ${source}.`,
          details: String(schemaError),
        })
    )
  );
}

/** Decodes package metadata during module initialization. */
function decodePackageManifestSummarySync(manifest: object): PackageManifestSummary {
  return Schema.decodeUnknownSync(PackageManifestSummarySchema)(manifest);
}

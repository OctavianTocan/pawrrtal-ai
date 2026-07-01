import { Effect, Option, Schema, SchemaTransformation } from 'effect';
import { ConfigError } from './Errors';

export type OptionalText = Option.Option<string>;

export type PersistedConfigValue =
  | string
  | number
  | boolean
  | null
  | ReadonlyArray<PersistedConfigValue>
  | { readonly [key: string]: PersistedConfigValue };

export type PersistedConfigRecord = Readonly<Record<string, PersistedConfigValue>>;

const PROFILE_NAME_PATTERN = /^(?!\.{1,2}$)[A-Za-z0-9][A-Za-z0-9._-]*$/;

export const TrimmedText = Schema.Trim.pipe(
  Schema.annotate({
    identifier: 'TrimmedText',
    title: 'Trimmed Text',
    description: 'Text normalized by trimming surrounding whitespace on decode.',
  })
);

export const OptionalTrimmedText = Schema.Trim.pipe(
  Schema.decodeTo(
    Schema.Option(Schema.String),
    SchemaTransformation.transform({
      decode: (text) => (text.length > 0 ? Option.some(text) : Option.none()),
      encode: (text) => Option.getOrElse(text, () => ''),
    })
  ),
  Schema.annotate({
    identifier: 'OptionalTrimmedText',
    title: 'Optional Trimmed Text',
    description: 'Trimmed text decoded to None when the value is empty.',
  })
);

export const OptionalTrimmedTextFromKey = Schema.OptionFromOptionalKey(Schema.Trim).pipe(
  Schema.decodeTo(
    Schema.Option(Schema.String),
    SchemaTransformation.transform({
      decode: (text) => Option.filter(text, (value) => value.length > 0),
      encode: (text) => text,
    })
  ),
  Schema.annotate({
    identifier: 'OptionalTrimmedTextFromKey',
    title: 'Optional Trimmed Text From Key',
    description: 'Optional object key decoded to None when the trimmed value is empty.',
  })
);

export const NonEmptyTrimmedText = Schema.Trim.check(
  Schema.isNonEmpty({
    expected: 'a non-empty string after trimming',
  })
).pipe(
  Schema.annotate({
    identifier: 'NonEmptyTrimmedText',
    title: 'Non-Empty Trimmed Text',
    description: 'Text that remains non-empty after trimming.',
  })
);

export const ProfileName = NonEmptyTrimmedText.check(
  Schema.isPattern(PROFILE_NAME_PATTERN, {
    expected: 'a safe profile path segment',
  })
).pipe(
  Schema.annotate({
    identifier: 'ProfileName',
    title: 'Profile Name',
    description: 'A safe Paw CLI profile identifier.',
  })
);

export const PersistedConfigValueSchema: Schema.Codec<PersistedConfigValue> = Schema.suspend(() =>
  Schema.Union([
    Schema.String,
    Schema.Number,
    Schema.Boolean,
    Schema.Null,
    Schema.Array(PersistedConfigValueSchema),
    Schema.Record(Schema.String, PersistedConfigValueSchema),
  ])
).pipe(
  Schema.annotate({
    identifier: 'PersistedConfigValue',
    title: 'Persisted Config Value',
    description: 'A TOML-compatible value allowed in Paw CLI config files.',
  })
);

export const PersistedConfigRecordSchema = Schema.Record(Schema.String, PersistedConfigValueSchema).pipe(
  Schema.annotate({
    identifier: 'PersistedConfigRecord',
    title: 'Persisted Config Record',
    description: 'Top-level TOML config object decoded before config-specific validation.',
  })
);

/** Decodes a safe persisted config tree from parsed TOML data. */
export function decodePersistedConfigRecord(
  value: object,
  source: string
): Effect.Effect<PersistedConfigRecord, ConfigError> {
  return Schema.decodeUnknownEffect(PersistedConfigRecordSchema)(value).pipe(
    Effect.mapError(
      (schemaError) =>
        new ConfigError({
          message: `Could not decode ${source}.`,
          details: String(schemaError),
        })
    )
  );
}

/** Normalizes a CLI option string through the shared optional text schema. */
export function normalizeTextOption(value: Option.Option<string>): OptionalText {
  return Option.flatMap(value, (text) => Schema.decodeUnknownOption(NonEmptyTrimmedText)(text));
}

/** Decodes a string as an optional trimmed value. */
export function decodeOptionalText(value: string): OptionalText {
  return Schema.decodeUnknownSync(OptionalTrimmedText)(value);
}

/** Converts an Option to the nullable public JSON shape. */
export function optionToNullable<A>(value: Option.Option<A>): A | null {
  return Option.getOrElse(value, () => null);
}

import { Effect, Option, Schema } from 'effect';
import type { Completions } from 'effect/unstable/cli';
import { Command } from 'effect/unstable/cli';
import { UsageError } from './Errors';
import { ExitCode } from './ExitCode';
import type { OutputMode } from './Output';

export type ParameterKind = 'string' | 'boolean' | 'integer' | 'choice' | 'file' | 'directory';
export type InputSource = 'inline' | 'file' | 'stdin' | 'editor';

export type ParameterMetadata = {
  readonly name: string;
  readonly description: string;
  readonly kind: ParameterKind;
  readonly required?: boolean;
  readonly aliases?: ReadonlyArray<string>;
  readonly choices?: ReadonlyArray<string>;
};

export type EnvironmentMetadata = {
  readonly name: string;
  readonly purpose: string;
};

export type ExampleMetadata = {
  readonly command: string;
  readonly description?: string;
};

export type StructuredOutputMetadata = {
  readonly mode: 'json';
  readonly contract: string;
  readonly description: string;
};

export type CommandMetadata = {
  readonly name: string;
  readonly summary: string;
  readonly description: string;
  readonly owner: string;
  readonly aliases?: ReadonlyArray<string>;
  readonly arguments?: ReadonlyArray<ParameterMetadata>;
  readonly flags?: ReadonlyArray<ParameterMetadata>;
  readonly subcommands?: ReadonlyArray<CommandMetadata>;
  readonly examples?: ReadonlyArray<ExampleMetadata>;
  readonly environment?: ReadonlyArray<EnvironmentMetadata>;
  readonly notes?: ReadonlyArray<string>;
  readonly outputModes: ReadonlyArray<OutputMode>;
  readonly structuredOutputs?: ReadonlyArray<StructuredOutputMetadata>;
  readonly inputSources?: ReadonlyArray<InputSource>;
  readonly exitCodes?: ReadonlyArray<ExitCode>;
};

export type EmptyCommandContext = Record<PropertyKey, never>;

export type CommandModule<
  Name extends string,
  Input = never,
  ContextInput = EmptyCommandContext,
  E = never,
  R = never,
> = {
  readonly command: Command.Command<Name, Input, ContextInput, E, R>;
  readonly metadata: CommandMetadata;
};

export const ParameterKindSchema = Schema.Literals([
  'string',
  'boolean',
  'integer',
  'choice',
  'file',
  'directory',
]).pipe(
  Schema.annotate({
    identifier: 'ParameterKind',
    title: 'Parameter Kind',
    description: 'Supported CLI parameter presentation kinds.',
  })
);
export const InputSourceSchema = Schema.Literals(['inline', 'file', 'stdin', 'editor']).pipe(
  Schema.annotate({
    identifier: 'InputSource',
    title: 'Input Source',
    description: 'Supported body/document input sources for CLI commands.',
  })
);
export const OutputModeSchema = Schema.Literals(['human', 'json', 'plain']).pipe(
  Schema.annotate({
    identifier: 'OutputMode',
    title: 'Output Mode',
    description: 'Supported stdout rendering modes.',
  })
);
export const ExitCodeSchema = Schema.Literals([
  ExitCode.success,
  ExitCode.local,
  ExitCode.usage,
  ExitCode.auth,
  ExitCode.external,
  ExitCode.verification,
]).pipe(
  Schema.annotate({
    identifier: 'ExitCode',
    title: 'Exit Code',
    description: 'Public Paw CLI exit-code contract.',
  })
);

export const ParameterMetadataSchema = Schema.Struct({
  name: Schema.NonEmptyString,
  description: Schema.NonEmptyString,
  kind: ParameterKindSchema,
  required: Schema.optionalKey(Schema.Boolean),
  aliases: Schema.optionalKey(Schema.Array(Schema.NonEmptyString)),
  choices: Schema.optionalKey(Schema.Array(Schema.NonEmptyString)),
}).pipe(
  Schema.annotate({
    identifier: 'ParameterMetadata',
    title: 'Parameter Metadata',
    description: 'Descriptor for a CLI argument or flag.',
  })
);

export const EnvironmentMetadataSchema = Schema.Struct({
  name: Schema.NonEmptyString,
  purpose: Schema.NonEmptyString,
}).pipe(
  Schema.annotate({
    identifier: 'EnvironmentMetadata',
    title: 'Environment Metadata',
    description: 'Descriptor for an environment variable that affects a command.',
  })
);

export const ExampleMetadataSchema = Schema.Struct({
  command: Schema.NonEmptyString,
  description: Schema.optionalKey(Schema.String),
}).pipe(
  Schema.annotate({
    identifier: 'ExampleMetadata',
    title: 'Example Metadata',
    description: 'Runnable command example shown in help and generated skills.',
  })
);

export const StructuredOutputMetadataSchema = Schema.Struct({
  mode: Schema.Literal('json'),
  contract: Schema.NonEmptyString,
  description: Schema.NonEmptyString,
}).pipe(
  Schema.annotate({
    identifier: 'StructuredOutputMetadata',
    title: 'Structured Output Metadata',
    description: 'Descriptor for a schema-backed structured output mode.',
  })
);

const MetadataNameSchema = Schema.Struct({
  name: Schema.String,
});

export const CommandMetadataSchema: Schema.Codec<CommandMetadata> = Schema.Struct({
  name: Schema.NonEmptyString,
  summary: Schema.NonEmptyString,
  description: Schema.NonEmptyString,
  owner: Schema.NonEmptyString,
  aliases: Schema.optionalKey(Schema.Array(Schema.NonEmptyString)),
  arguments: Schema.optionalKey(Schema.Array(ParameterMetadataSchema)),
  flags: Schema.optionalKey(Schema.Array(ParameterMetadataSchema)),
  subcommands: Schema.optionalKey(
    Schema.Array(Schema.suspend((): Schema.Codec<CommandMetadata> => CommandMetadataSchema))
  ),
  examples: Schema.optionalKey(Schema.Array(ExampleMetadataSchema)),
  environment: Schema.optionalKey(Schema.Array(EnvironmentMetadataSchema)),
  notes: Schema.optionalKey(Schema.Array(Schema.NonEmptyString)),
  outputModes: Schema.Array(OutputModeSchema),
  structuredOutputs: Schema.optionalKey(Schema.Array(StructuredOutputMetadataSchema)),
  inputSources: Schema.optionalKey(Schema.Array(InputSourceSchema)),
  exitCodes: Schema.optionalKey(Schema.Array(ExitCodeSchema)),
}).pipe(
  Schema.annotate({
    identifier: 'CommandMetadata',
    title: 'Command Metadata',
    description: 'Canonical command descriptor used for help, completions, and generated skills.',
  })
);

export const GLOBAL_FLAG_METADATA: ReadonlyArray<ParameterMetadata> = [
  {
    name: 'help',
    description: 'Print help for the current command path',
    kind: 'boolean',
    aliases: ['h'],
  },
  {
    name: 'version',
    description: 'Print CLI version',
    kind: 'boolean',
    aliases: ['V'],
  },
  {
    name: 'verbose',
    description: 'Print expanded diagnostics and source chains',
    kind: 'boolean',
    aliases: ['v'],
  },
  {
    name: 'profile',
    description: 'Run this invocation against a specific profile',
    kind: 'string',
  },
  {
    name: 'backend-url',
    description: 'Run this invocation against a specific backend target',
    kind: 'string',
  },
];

export const AUTOMATION_FLAG_METADATA: ReadonlyArray<ParameterMetadata> = [
  {
    name: 'json',
    description: 'Print structured JSON to stdout',
    kind: 'boolean',
  },
  {
    name: 'plain',
    description: 'Print tab-separated values to stdout with no headers',
    kind: 'boolean',
  },
];

/**
 * Builds root command metadata from registered module metadata.
 *
 * @param subcommands - Supported command metadata for the current CLI slice.
 * @returns Metadata for the root `paw` command.
 */
export function makeRootMetadata(subcommands: ReadonlyArray<CommandMetadata>): CommandMetadata {
  return {
    name: 'paw',
    summary: 'Operate Pawrrtal from a small, agent-friendly CLI',
    description:
      'Operate Pawrrtal from a small, agent-friendly CLI. This first slice exposes local health, active context, shell completions, and stable output/config conventions.',
    owner: '@pawrrtal/cli',
    flags: GLOBAL_FLAG_METADATA,
    subcommands,
    examples: [
      { command: 'paw doctor', description: 'Check local CLI readiness' },
      { command: 'paw context --json', description: 'Print active context as JSON' },
      { command: 'paw completions zsh', description: 'Print zsh completions' },
    ],
    environment: [
      { name: 'PAW_HOME', purpose: 'Override the CLI state root for config and cache' },
      { name: 'PAW_PROFILE', purpose: 'Set the active profile when --profile is not supplied' },
      { name: 'PAW_BACKEND_URL', purpose: 'Override the backend target for this invocation' },
      { name: 'XDG_CONFIG_HOME', purpose: 'Fallback config root when PAW_HOME is unset' },
      { name: 'XDG_CACHE_HOME', purpose: 'Fallback cache root when PAW_HOME is unset' },
    ],
    notes: [
      '`-V` prints the CLI version; `-v` enables verbose diagnostics.',
      '`--profile` and `--backend-url` affect only the current invocation.',
    ],
    outputModes: ['human'],
    exitCodes: [ExitCode.success, ExitCode.local, ExitCode.usage, ExitCode.external],
  };
}

/**
 * Decodes command metadata before help, completions, and skill generation consume it.
 *
 * @param metadata - Metadata object to validate.
 * @returns Schema-validated command metadata.
 */
export function validateCommandMetadata(metadata: object): Effect.Effect<CommandMetadata, UsageError> {
  return Schema.decodeUnknownEffect(CommandMetadataSchema)(metadata).pipe(
    Effect.mapError(
      (schemaError) =>
        new UsageError({
          message: `Invalid command metadata for '${metadataName(metadata)}'.`,
          details: String(schemaError),
        })
    )
  );
}

/**
 * Synchronously validates source-owned metadata during registry construction.
 *
 * @param metadata - Command metadata from source code.
 * @returns Schema-validated metadata.
 */
export function assertCommandMetadata(metadata: CommandMetadata): CommandMetadata {
  return Schema.decodeUnknownSync(CommandMetadataSchema)(metadata);
}

/**
 * Applies metadata-backed presentation fields to an Effect command.
 *
 * @param command - Command to decorate.
 * @param metadata - Canonical command metadata for descriptions and examples.
 * @returns Command with Effect presentation fields derived from metadata.
 */
export function applyCommandMetadata<const Name extends string, Input, ContextInput, E, R>(
  command: Command.Command<Name, Input, ContextInput, E, R>,
  metadata: CommandMetadata
): Command.Command<Name, Input, ContextInput, E, R> {
  return command.pipe(
    Command.withDescription(metadata.description),
    Command.withShortDescription(metadata.summary),
    Command.withExamples(metadata.examples ?? [])
  );
}

/**
 * Converts Paw command metadata to Effect completion descriptors.
 *
 * @param metadata - Command metadata used as the completion source.
 * @returns Descriptor accepted by Effect's shell completion generator.
 */
export function metadataToCompletionDescriptor(metadata: CommandMetadata): Completions.CommandDescriptor {
  const validMetadata = assertCommandMetadata(metadata);
  return {
    name: validMetadata.name,
    description: validMetadata.summary,
    flags: (validMetadata.flags ?? []).map(parameterToFlagDescriptor),
    arguments: (validMetadata.arguments ?? []).map(parameterToArgumentDescriptor),
    subcommands: (validMetadata.subcommands ?? []).map(metadataToCompletionDescriptor),
  };
}

/** Returns a best-effort metadata name for diagnostics. */
function metadataName(metadata: object): string {
  return Option.match(Schema.decodeUnknownOption(MetadataNameSchema)(metadata), {
    onNone: () => 'unidentified',
    onSome: (value) => value.name,
  });
}

/** Converts a metadata parameter to a completion flag. */
function parameterToFlagDescriptor(parameter: ParameterMetadata): Completions.FlagDescriptor {
  return {
    name: parameter.name,
    aliases: parameter.aliases ?? [],
    description: parameter.description,
    type: parameterToFlagType(parameter),
  };
}

/** Converts a metadata parameter to a completion argument. */
function parameterToArgumentDescriptor(parameter: ParameterMetadata): Completions.ArgumentDescriptor {
  return {
    name: parameter.name,
    description: parameter.description,
    required: parameter.required ?? true,
    variadic: false,
    type: parameterToArgumentType(parameter),
  };
}

/** Converts a metadata kind to an Effect completion flag type. */
function parameterToFlagType(parameter: ParameterMetadata): Completions.FlagType {
  switch (parameter.kind) {
    case 'boolean':
      return { _tag: 'Boolean' };
    case 'integer':
      return { _tag: 'Integer' };
    case 'choice':
      return { _tag: 'Choice', values: parameter.choices ?? [] };
    case 'file':
      return { _tag: 'Path', pathType: 'file' };
    case 'directory':
      return { _tag: 'Path', pathType: 'directory' };
    case 'string':
      return { _tag: 'String' };
    default:
      return assertNever(parameter.kind);
  }
}

/** Converts a metadata kind to an Effect completion argument type. */
function parameterToArgumentType(parameter: ParameterMetadata): Completions.ArgumentType {
  switch (parameter.kind) {
    case 'integer':
      return { _tag: 'Integer' };
    case 'choice':
      return { _tag: 'Choice', values: parameter.choices ?? [] };
    case 'file':
      return { _tag: 'Path', pathType: 'file' };
    case 'directory':
      return { _tag: 'Path', pathType: 'directory' };
    case 'boolean':
    case 'string':
      return { _tag: 'String' };
    default:
      return assertNever(parameter.kind);
  }
}

/** Fails when a metadata union grows without updating completion conversion. */
function assertNever(value: never): never {
  throw new Error(`Unhandled parameter kind: ${String(value)}`);
}

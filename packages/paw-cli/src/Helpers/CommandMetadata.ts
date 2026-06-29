import type * as Command from 'effect/unstable/cli/Command';
import type * as Completions from 'effect/unstable/cli/Completions';
import { ExitCode } from './ExitCode.ts';
import type { OutputMode } from './Output.ts';

export type ParameterKind = 'string' | 'boolean' | 'integer' | 'choice' | 'file' | 'directory';
export type InputSource = 'flag' | 'file' | 'stdin' | 'editor';

export interface ParameterMetadata {
  readonly name: string;
  readonly description: string;
  readonly kind: ParameterKind;
  readonly required?: boolean;
  readonly aliases?: ReadonlyArray<string>;
  readonly choices?: ReadonlyArray<string>;
}

export interface EnvironmentMetadata {
  readonly name: string;
  readonly purpose: string;
}

export interface ExampleMetadata {
  readonly command: string;
  readonly description?: string;
}

export interface CommandMetadata {
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
  readonly outputModes: ReadonlyArray<OutputMode>;
  readonly inputSources?: ReadonlyArray<InputSource>;
  readonly exitCodes?: ReadonlyArray<ExitCode>;
}

export interface CommandModule {
  readonly command: Command.Command.Any;
  readonly metadata: CommandMetadata;
}

const GLOBAL_FLAGS: ReadonlyArray<ParameterMetadata> = [
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

/** Build root command metadata from registered module metadata. */
export function makeRootMetadata(subcommands: ReadonlyArray<CommandMetadata>): CommandMetadata {
  return {
    name: 'paw',
    summary: 'Operate Pawrrtal from a small, agent-friendly CLI',
    description:
      'Operate Pawrrtal from a small, agent-friendly CLI. This first slice exposes local health, active context, shell completions, and stable output/config conventions.',
    owner: '@pawrrtal/cli',
    flags: GLOBAL_FLAGS,
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
    outputModes: ['human'],
    exitCodes: [ExitCode.success, ExitCode.local, ExitCode.usage, ExitCode.external],
  };
}

/** Convert Paw metadata to Effect's completion descriptor shape. */
export function metadataToCompletionDescriptor(metadata: CommandMetadata): Completions.CommandDescriptor {
  return {
    name: metadata.name,
    description: metadata.summary,
    flags: (metadata.flags ?? []).map(parameterToFlagDescriptor),
    arguments: (metadata.arguments ?? []).map(parameterToArgumentDescriptor),
    subcommands: (metadata.subcommands ?? []).map(metadataToCompletionDescriptor),
  };
}

function parameterToFlagDescriptor(parameter: ParameterMetadata): Completions.FlagDescriptor {
  return {
    name: parameter.name,
    aliases: parameter.aliases ?? [],
    description: parameter.description,
    type: parameterToFlagType(parameter),
  };
}

function parameterToArgumentDescriptor(parameter: ParameterMetadata): Completions.ArgumentDescriptor {
  return {
    name: parameter.name,
    description: parameter.description,
    required: parameter.required ?? true,
    variadic: false,
    type: parameterToArgumentType(parameter),
  };
}

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
  }
}

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
  }
}

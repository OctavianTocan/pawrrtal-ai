import type { CommandMetadata, ParameterMetadata } from './CommandMetadata';

/** Formats root help from command metadata. */
export function formatHelp(input: { readonly metadata: CommandMetadata }): string {
  return formatRootHelp(input.metadata);
}

/** Formats root help from metadata. */
export function formatRootHelp(metadata: CommandMetadata): string {
  return [
    'SUMMARY',
    `  ${metadata.summary}`,
    '',
    'DESCRIPTION',
    `  ${metadata.description}`,
    '',
    'USAGE',
    '  paw <command> [options]',
    '',
    formatOptions('GLOBAL OPTIONS', metadata.flags ?? []),
    'COMMANDS',
    ...(metadata.subcommands ?? []).map(formatCommandListItem),
    '',
    formatEnvironment(metadata.environment ?? []),
    formatNotes(metadata.notes ?? []),
    formatExamples(metadata),
  ]
    .filter((line) => line.length > 0)
    .join('\n');
}

/** Formats command help from metadata. */
export function formatCommandHelp(metadata: CommandMetadata): string {
  return [
    'SUMMARY',
    `  ${metadata.summary}`,
    '',
    'DESCRIPTION',
    `  ${metadata.description}`,
    '',
    'USAGE',
    `  paw ${metadata.name}${formatArgumentsUsage(metadata)} [options]`,
    '',
    formatArguments(metadata.arguments ?? []),
    formatOptions('OPTIONS', metadata.flags ?? []),
    formatEnvironment(metadata.environment ?? []),
    formatNotes(metadata.notes ?? []),
    formatExamples(metadata),
  ]
    .filter((line) => line.length > 0)
    .join('\n');
}

/** Formats one command list line. */
function formatCommandListItem(metadata: CommandMetadata): string {
  const aliases = metadata.aliases?.length ? `, ${metadata.aliases.join(', ')}` : '';
  return `  ${metadata.name}${aliases}  ${metadata.summary}`;
}

/** Formats positional usage. */
function formatArgumentsUsage(metadata: CommandMetadata): string {
  const args = metadata.arguments ?? [];
  if (args.length === 0) {
    return '';
  }
  return ` ${args.map((arg) => `<${arg.name}>`).join(' ')}`;
}

/** Formats positional argument details. */
function formatArguments(args: ReadonlyArray<ParameterMetadata>): string {
  if (args.length === 0) {
    return '';
  }
  return ['ARGUMENTS', ...args.map((arg) => `  ${arg.name}  ${arg.description}`), ''].join('\n');
}

/** Formats option details. */
function formatOptions(label: string, flags: ReadonlyArray<ParameterMetadata>): string {
  if (flags.length === 0) {
    return '';
  }
  return [label, ...flags.map(formatFlag), ''].join('\n');
}

/** Formats environment variables that affect a command. */
function formatEnvironment(environment: NonNullable<CommandMetadata['environment']>): string {
  if (environment.length === 0) {
    return '';
  }
  return ['ENVIRONMENT', ...environment.map((entry) => `  ${entry.name}  ${entry.purpose}`), ''].join('\n');
}

/** Formats command notes. */
function formatNotes(notes: ReadonlyArray<string>): string {
  if (notes.length === 0) {
    return '';
  }
  return ['NOTES', ...notes.map((note) => `  ${note}`), ''].join('\n');
}

/** Formats one option line. */
function formatFlag(flag: ParameterMetadata): string {
  const aliases = flag.aliases?.map((alias) => `-${alias}, `).join('') ?? '';
  const valueHint = flag.kind === 'boolean' ? '' : ` ${flag.kind}`;
  return `  ${aliases}--${flag.name}${valueHint}  ${flag.description}`;
}

/** Formats command examples. */
function formatExamples(metadata: CommandMetadata): string {
  if (!metadata.examples?.length) {
    return '';
  }
  return ['EXAMPLES', ...metadata.examples.flatMap(formatExample)].join('\n');
}

/** Formats one command example. */
function formatExample(example: { readonly command: string; readonly description?: string }): ReadonlyArray<string> {
  return example.description ? [`  # ${example.description}`, `  ${example.command}`] : [`  ${example.command}`];
}

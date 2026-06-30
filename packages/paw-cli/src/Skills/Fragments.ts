import type { CommandRegistry } from '../Commands';
import { DefaultCommandRegistry } from '../Commands';
import type { CommandMetadata, EnvironmentMetadata, ParameterMetadata } from '../Helpers/CommandMetadata';
import { ExitCode } from '../Helpers/ExitCode';

export type SkillFragment = {
  readonly name: string;
  readonly description: string;
  readonly extraFrontmatter: ReadonlyArray<string>;
  readonly body: string;
  readonly relativePath: string;
};

const SOURCE_PATH = 'packages/paw-cli/src/Skills/Fragments.ts';

const PAW_DESCRIPTION =
  'Use when running the Bun-backed Paw CLI: local health, active context, shell completions, output modes, profiles, and verification of the supported command surface.';

const DOMAIN_CLI_DESCRIPTION =
  'Use when changing, extending, testing, or reviewing the Bun-backed Paw CLI package and its generated agent skills.';

/**
 * Builds generated skill fragments from the live CLI command registry.
 *
 * @param registry - Command registry whose metadata should be documented.
 * @returns Skill fragments compatible with `packages/ci/skill-gen`.
 */
export function getSkillFragments(registry: CommandRegistry = DefaultCommandRegistry): ReadonlyArray<SkillFragment> {
  return [makePawSkill(registry.rootMetadata), makeDomainCliSkill(registry.rootMetadata)];
}

/** Builds the user-facing CLI usage skill. */
function makePawSkill(root: CommandMetadata): SkillFragment {
  return {
    name: 'paw',
    description: PAW_DESCRIPTION,
    extraFrontmatter: [
      'paths:',
      '  - "packages/paw-cli/**"',
      '  - "scripts/paw"',
      '  - "justfile"',
      '  - "specs/004-effect-paw-cli/**"',
    ],
    body: [
      '# paw',
      '',
      'Use `paw` when you need the supported Pawrrtal CLI surface. This CLI is a Bun-backed Effect v4 package at `packages/paw-cli`; do not route new work through the deleted Python CLI.',
      '',
      '## Commands',
      '',
      commandTable(root.subcommands ?? []),
      '',
      '## Common Usage',
      '',
      '```bash',
      'just paw --help',
      'just paw doctor --json',
      'just paw context --json',
      'just paw whoami --plain',
      'just paw completions zsh',
      'bun run --filter @pawrrtal/cli start -- doctor',
      '```',
      '',
      '## Global Options',
      '',
      parameterTable(root.flags ?? []),
      '',
      '## Output Modes',
      '',
      '- Human output is the default.',
      '- `--json` prints structured JSON to stdout.',
      '- `--plain` prints tab-separated rows to stdout when a command supports it.',
      '- Progress, warnings, validation errors, and runtime errors belong on stderr.',
      '- `--json` and `--plain` are mutually exclusive.',
      '',
      '## Environment',
      '',
      environmentList(root.environment ?? []),
      '',
      '## Exit Codes',
      '',
      exitCodeTable(root.exitCodes ?? []),
      '',
      '## Verification',
      '',
      '```bash',
      'bun run --filter @pawrrtal/cli typecheck',
      'bun run --filter @pawrrtal/cli test',
      'bun run --filter @pawrrtal/cli check',
      'bun run skill-gen:check',
      'just paw-cli-check',
      '```',
      '',
      '## Pitfalls',
      '',
      '- `-V` prints the CLI version; `-v` enables verbose diagnostics.',
      '- `PAW_HOME` overrides both config and cache roots for the invocation.',
      '- `paw context` and `paw whoami` must not print secret values.',
      '- `paw doctor` is local-only in this slice and may warn when optional state has not been generated yet.',
    ].join('\n'),
    relativePath: SOURCE_PATH,
  };
}

/** Builds the code-domain skill for changing the CLI package. */
function makeDomainCliSkill(root: CommandMetadata): SkillFragment {
  return {
    name: 'domain-cli',
    description: DOMAIN_CLI_DESCRIPTION,
    extraFrontmatter: [
      'paths:',
      '  - "packages/paw-cli/**"',
      '  - "packages/ci/skill-gen/**"',
      '  - "scripts/paw"',
      '  - "justfile"',
      '  - "specs/004-effect-paw-cli/**"',
    ],
    body: [
      '# domain-cli',
      '',
      'Use this skill before changing the Paw CLI package. The CLI is a standalone Bun-first Effect v4 package at `packages/paw-cli`; feature-owned commands are added only when the owning feature needs them.',
      '',
      '## Package Shape',
      '',
      '```text',
      'packages/paw-cli/',
      '|-- src/',
      '|   |-- Main.ts',
      '|   |-- Cli.ts',
      '|   |-- Commands.ts',
      '|   |-- Helpers/',
      '|   |-- Infrastructure/',
      '|   |-- Modules/<Name>/',
      '|   `-- Skills/Fragments.ts',
      '`-- test/',
      '    |-- unit/',
      '    |-- integration/',
      '    `-- fixtures/',
      '```',
      '',
      '## Current Command Surface',
      '',
      commandTable(root.subcommands ?? []),
      '',
      '## Rules',
      '',
      '- Keep `effect`, `@effect/platform-bun`, and `@effect/vitest` on the same latest verified v4 beta in `packages/paw-cli/package.json`.',
      '- Use Bun runtime services for CLI execution; do not add `@effect/platform-node` or `node:*` imports to `packages/paw-cli/src`.',
      '- Keep shared runtime services under `src/Infrastructure/`; feature modules should not import shared services from each other.',
      '- Keep command modules under `src/Modules/<Name>/` with `Command.ts`, plus `Domain.ts` and focused helpers only when the command needs them.',
      '- Register command modules in `src/Commands.ts`; do not create placeholder command groups for future product ideas.',
      '- Keep command metadata next to the command implementation and make generated skills read from that metadata.',
      '- Use tagged errors from `src/Helpers/Errors.ts` and map failures to the public exit-code contract.',
      '- Use `src/Helpers/Output.ts` for `human`, `json`, and `plain` rendering.',
      '- Use `src/Helpers/Config.ts` for profile, state-root, TOML, and no-secret config behavior.',
      '- Treat first-slice helpers like `InputSource.ts`, `writeProfileConfig()`, and unused error tags as tested policy helpers until a feature-owned command needs them.',
      '- Use `@effect/vitest` for tests that directly exercise Effect values or services; plain Vitest is fine for process integration and pure synchronous assertions.',
      '- Remove old Python CLI references instead of bridging, shelling out, or maintaining compatibility shims.',
      '',
      '## Add A Command Group',
      '',
      '1. Create `packages/paw-cli/src/Modules/<Name>/Command.ts` and a `Domain.ts` when the command needs domain types or services.',
      '2. Define command metadata with `name`, `summary`, `description`, `owner`, flags, examples, output modes, and exit codes.',
      '3. Build the command with `effect/unstable/cli` primitives and Effect handlers.',
      '4. Register the module in `packages/paw-cli/src/Commands.ts`.',
      '5. Add unit and integration tests under `packages/paw-cli/test/`.',
      '6. Run the CLI checks and regenerate skills.',
      '',
      '## Skill Generation',
      '',
      '`packages/paw-cli/src/Skills/Fragments.ts` exports dynamic fragments for `paw` and `domain-cli`. `packages/ci/skill-gen` loads those fragments and merges them with normal `//<skill-gen>` source markers, so generated skills stay aligned with the command registry.',
      '',
      '```bash',
      'bun run skill-gen:generate',
      'bun run skill-gen:check',
      'bun run skill-gen:e2e-test',
      '```',
      '',
      '## Required Checks',
      '',
      '```bash',
      'bun run --filter @pawrrtal/cli typecheck',
      'bun run --filter @pawrrtal/cli test',
      'bun run --filter @pawrrtal/cli check',
      'bun run skill-gen:check',
      'just paw-cli-check',
      '```',
    ].join('\n'),
    relativePath: SOURCE_PATH,
  };
}

/** Renders a markdown table for command metadata. */
function commandTable(commands: ReadonlyArray<CommandMetadata>): string {
  if (commands.length === 0) {
    return 'No commands are registered.';
  }

  return [
    '| Command | Aliases | Summary |',
    '| --- | --- | --- |',
    ...commands.map((command) => {
      const aliases = command.aliases?.join(', ') ?? '';
      return `| \`paw ${command.name}${argumentUsage(command.arguments ?? [])}\` | ${aliases || '-'} | ${command.summary} |`;
    }),
  ].join('\n');
}

/** Renders a markdown table for flag metadata. */
function parameterTable(parameters: ReadonlyArray<ParameterMetadata>): string {
  if (parameters.length === 0) {
    return 'No options are declared.';
  }

  return [
    '| Option | Meaning |',
    '| --- | --- |',
    ...parameters.map((parameter) => `| ${parameterName(parameter)} | ${parameter.description} |`),
  ].join('\n');
}

/** Renders environment variable metadata as markdown bullets. */
function environmentList(environment: ReadonlyArray<EnvironmentMetadata>): string {
  if (environment.length === 0) {
    return '- No environment variables are documented.';
  }

  return environment.map((entry) => `- \`${entry.name}\`: ${entry.purpose}.`).join('\n');
}

/** Renders known exit-code meanings. */
function exitCodeTable(codes: ReadonlyArray<ExitCode>): string {
  const values = codes.length > 0 ? codes : Object.values(ExitCode);
  return [
    '| Code | Meaning |',
    '| --- | --- |',
    ...values.map((code) => `| ${code} | ${exitCodeMeaning(code)} |`),
  ].join('\n');
}

/** Renders positional arguments for command usage. */
function argumentUsage(parameters: ReadonlyArray<ParameterMetadata>): string {
  if (parameters.length === 0) {
    return '';
  }
  return ` ${parameters.map((parameter) => `<${parameter.name}>`).join(' ')}`;
}

/** Renders one option name and aliases. */
function parameterName(parameter: ParameterMetadata): string {
  const aliases = parameter.aliases?.map((alias) => `\`-${alias}\``) ?? [];
  return [...aliases, `\`--${parameter.name}\``].join(', ');
}

/** Returns the public meaning for an exit code. */
function exitCodeMeaning(code: ExitCode): string {
  switch (code) {
    case ExitCode.success:
      return 'Success';
    case ExitCode.local:
      return 'Internal, local, or config error';
    case ExitCode.usage:
      return 'Usage, validation, or ambiguous input source';
    case ExitCode.auth:
      return 'Auth, permission, or active-context denial';
    case ExitCode.external:
      return 'Backend, network, external process, or dependency failure';
    case ExitCode.verification:
      return 'Future assertion or verification failure';
    default:
      return assertNever(code);
  }
}

/** Fails when the exit-code contract changes without skill text support. */
function assertNever(code: never): never {
  throw new Error(`Unhandled exit code: ${String(code)}`);
}

import { Context, Effect, FileSystem, Layer, Option, Path } from 'effect';
import type { PawCliError, UsageError } from './Errors';
import { ConfigError, failConfig, failUsage } from './Errors';
import type { RootOptions } from './Options';

export type AuthState = 'not_applicable' | 'unknown' | 'authenticated' | 'unauthenticated';

export type ConfigSource = {
  readonly key: string;
  readonly source: string;
  readonly value: string | null;
};

export type ActiveContext = {
  readonly profile: string;
  readonly configRoot: string;
  readonly cacheRoot: string;
  readonly backendTarget: string | null;
  readonly backendTargetSource: string | null;
  readonly backendTargetUnsetReason: string | null;
  readonly authState: AuthState;
  readonly configSources: ReadonlyArray<ConfigSource>;
};

export type ResolveContextOptions = {
  readonly rootOptions: RootOptions;
  readonly cwd?: string;
};

export type ProfileConfigInput = {
  readonly profile: string;
  readonly configRoot: string;
  readonly values: Readonly<Record<string, string | undefined>>;
};

export type CliProcessShape = {
  readonly cwd: string;
  readonly env: Readonly<Record<string, string | undefined>>;
  readonly home: string;
};

type TomlConfig = {
  readonly profile?: string;
  readonly backendUrl?: string;
};

type StateRoots = {
  readonly configRoot: string;
  readonly cacheRoot: string;
  readonly configSource: string;
  readonly cacheSource: string;
};

type SourceValue = {
  readonly source: string;
  readonly value: string;
};

const DEFAULT_PROFILE = 'default';
const CONFIG_FILE = 'config.toml';
const PROJECT_CONFIG_FILE = 'paw.toml';
const PROFILE_DIR = 'profiles';
const PROFILE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** Provides process-level facts that the Bun entrypoint reads once. */
export class CliProcess extends Context.Service<CliProcess, CliProcessShape>()('@pawrrtal/cli/Process') {}

/** Provides Bun process facts as an Effect layer. */
export const CliProcessLive: Layer.Layer<CliProcess> = Layer.sync(CliProcess, () => ({
  cwd: process.cwd(),
  env: Bun.env,
  home: Bun.env.HOME ?? Bun.env.USERPROFILE ?? '/tmp',
}));

/**
 * Resolves the active Paw CLI context from flags, environment, and TOML files.
 *
 * @param options - Root command options and optional working directory override.
 * @returns Active context with source metadata and no secret values.
 */
export function resolveActiveContext(
  options: ResolveContextOptions
): Effect.Effect<ActiveContext, PawCliError, CliProcess | FileSystem.FileSystem | Path.Path> {
  return Effect.gen(function* () {
    const processInfo = yield* CliProcess;
    const pathService = yield* Path.Path;
    const cwd = pathService.resolve(options.cwd ?? processInfo.cwd);
    const stateRoots = resolveStateRoots({ env: processInfo.env, home: processInfo.home, path: pathService });
    const projectFile = yield* findUp(cwd, PROJECT_CONFIG_FILE);
    const projectConfig = yield* readTomlConfig(projectFile);
    const userConfigPath = pathService.join(stateRoots.configRoot, CONFIG_FILE);
    const userConfig = yield* readTomlConfig(userConfigPath);
    const profile = yield* resolveProfile({
      rootOptions: options.rootOptions,
      env: processInfo.env,
      projectFile,
      projectConfig,
      userConfig,
      userConfigPath,
    });
    const profileConfigPath = pathService.join(stateRoots.configRoot, PROFILE_DIR, `${profile.value}.toml`);
    const profileConfig = yield* readTomlConfig(profileConfigPath);
    const backendTarget = resolveBackendTarget({
      rootOptions: options.rootOptions,
      env: processInfo.env,
      projectFile,
      projectConfig,
      profileConfig,
      profileConfigPath,
      userConfig,
      userConfigPath,
    });

    return {
      profile: profile.value,
      configRoot: stateRoots.configRoot,
      cacheRoot: stateRoots.cacheRoot,
      backendTarget: backendTarget?.value ?? null,
      backendTargetSource: backendTarget?.source ?? null,
      backendTargetUnsetReason: backendTarget ? null : 'No backend target configured.',
      authState: 'not_applicable',
      configSources: [
        { key: 'profile', source: profile.source, value: profile.value },
        {
          key: 'backendTarget',
          source: backendTarget?.source ?? 'unset',
          value: backendTarget?.value ?? null,
        },
        { key: 'configRoot', source: stateRoots.configSource, value: stateRoots.configRoot },
        { key: 'cacheRoot', source: stateRoots.cacheSource, value: stateRoots.cacheRoot },
      ],
    } satisfies ActiveContext;
  });
}

/**
 * Rejects profile config values that include secret-looking keys.
 *
 * @param value - Profile config object to inspect.
 * @param path - Logical path used in validation messages.
 * @returns Effect that succeeds when no secret-looking key is present.
 */
export function validateNoSecrets(value: unknown, path = 'config'): Effect.Effect<void, ConfigError> {
  const secretPath = findSecretPath(value, path);
  return secretPath ? failConfig(`Profile config cannot persist secret field '${secretPath}'.`) : Effect.void;
}

/**
 * Writes a non-secret profile TOML file under the resolved config root.
 *
 * @param input - Profile name, config root, and string values to persist.
 * @returns Absolute path to the written profile config file.
 */
export function writeProfileConfig(
  input: ProfileConfigInput
): Effect.Effect<string, PawCliError, FileSystem.FileSystem | Path.Path> {
  return Effect.gen(function* () {
    const profile = yield* validateProfileName(input.profile, 'profile');
    yield* validateNoSecrets(input.values);
    const fs = yield* FileSystem.FileSystem;
    const pathService = yield* Path.Path;
    const profileDir = pathService.join(input.configRoot, PROFILE_DIR);
    yield* fs
      .makeDirectory(profileDir, { recursive: true })
      .pipe(
        Effect.mapError(
          (error) => new ConfigError({ message: `Could not create profile config directory.`, details: String(error) })
        )
      );

    const filePath = pathService.join(profileDir, `${profile}.toml`);
    const body = Object.entries(input.values)
      .filter((entry): entry is [string, string] => nonEmpty(entry[1]) !== undefined)
      .map(([key, value]) => `${key} = ${JSON.stringify(value)}`)
      .join('\n');

    yield* fs
      .writeFileString(filePath, `${body}\n`)
      .pipe(
        Effect.mapError(
          (error) => new ConfigError({ message: `Could not write profile config.`, details: String(error) })
        )
      );

    return filePath;
  });
}

/**
 * Validates a profile identifier before it is used in config paths.
 *
 * @param value - Profile name from flags, environment, TOML, or write input.
 * @param source - Source label used in diagnostics.
 * @returns Clean profile name, or a usage error when it is not a safe segment.
 */
export function validateProfileName(value: string, source: string): Effect.Effect<string, UsageError> {
  const clean = nonEmpty(value);
  if (!clean || clean === '.' || clean === '..' || !PROFILE_NAME_PATTERN.test(clean)) {
    return failUsage(
      `Invalid profile name '${value}'.`,
      'Start with a letter or number, then use letters, numbers, dot, dash, or underscore.',
      `Profile source: ${source}`
    );
  }

  return Effect.succeed(clean);
}

/** Resolves state roots from Paw and XDG environment variables. */
function resolveStateRoots(input: {
  readonly env: Readonly<Record<string, string | undefined>>;
  readonly home: string;
  readonly path: Path.Path;
}): StateRoots {
  const { env, home, path } = input;
  const pawHome = nonEmpty(env.PAW_HOME);
  if (pawHome) {
    const root = path.resolve(pawHome);
    return {
      configRoot: path.join(root, 'config'),
      cacheRoot: path.join(root, 'cache'),
      configSource: 'env:PAW_HOME',
      cacheSource: 'env:PAW_HOME',
    };
  }

  const xdgConfig = nonEmpty(env.XDG_CONFIG_HOME);
  const xdgCache = nonEmpty(env.XDG_CACHE_HOME);
  return {
    configRoot: path.join(path.resolve(xdgConfig ?? path.join(home, '.config')), 'pawrrtal'),
    cacheRoot: path.join(path.resolve(xdgCache ?? path.join(home, '.cache')), 'pawrrtal'),
    configSource: xdgConfig ? 'env:XDG_CONFIG_HOME' : 'home-default',
    cacheSource: xdgCache ? 'env:XDG_CACHE_HOME' : 'home-default',
  };
}

/** Reads a TOML config file, returning undefined when the file is absent. */
function readTomlConfig(
  filePath: string | undefined
): Effect.Effect<TomlConfig | undefined, ConfigError, FileSystem.FileSystem> {
  if (!filePath) {
    return Effect.succeed(undefined);
  }

  return Effect.gen(function* () {
    const fs = yield* FileSystem.FileSystem;
    const exists = yield* fs.exists(filePath).pipe(Effect.orElseSucceed(() => false));
    if (!exists) {
      return undefined;
    }

    const source = yield* fs
      .readFileString(filePath)
      .pipe(
        Effect.mapError((error) => new ConfigError({ message: `Could not read ${filePath}.`, details: String(error) }))
      );
    return yield* parseTomlConfig(source, filePath);
  });
}

/** Parses supported Paw TOML keys from file content. */
function parseTomlConfig(source: string, filePath: string): Effect.Effect<TomlConfig, ConfigError> {
  return Effect.try({
    try: () => {
      const parsedToml = Bun.TOML.parse(source) as unknown;
      if (!isRecord(parsedToml)) {
        return {};
      }

      return compactTomlConfig({
        profile: readString(parsedToml, 'profile'),
        backendUrl: readString(parsedToml, 'backend_url') ?? readString(parsedToml, 'backendUrl'),
      });
    },
    catch: (error) => new ConfigError({ message: `Could not parse ${filePath}.`, details: String(error) }),
  });
}

/** Finds a file by walking from a directory to the filesystem root. */
function findUp(
  startDirectory: string,
  fileName: string
): Effect.Effect<string | undefined, never, FileSystem.FileSystem | Path.Path> {
  return Effect.gen(function* () {
    const fs = yield* FileSystem.FileSystem;
    const pathService = yield* Path.Path;
    let current = startDirectory;
    while (true) {
      const candidate = pathService.join(current, fileName);
      const exists = yield* fs.exists(candidate).pipe(Effect.orElseSucceed(() => false));
      if (exists) {
        return candidate;
      }

      const parent = pathService.dirname(current);
      if (parent === current || pathService.parse(current).root === current) {
        return undefined;
      }
      current = parent;
    }
  });
}

/** Resolves the active profile source and value. */
function resolveProfile(input: {
  readonly rootOptions: RootOptions;
  readonly env: Readonly<Record<string, string | undefined>>;
  readonly projectFile: string | undefined;
  readonly projectConfig: TomlConfig | undefined;
  readonly userConfig: TomlConfig | undefined;
  readonly userConfigPath: string;
}): Effect.Effect<SourceValue, UsageError> {
  const profile = firstValue([
    sourceValue('flag', optionString(input.rootOptions.profile)),
    sourceValue('env:PAW_PROFILE', input.env.PAW_PROFILE),
    sourceValue(input.projectFile ? `project:${input.projectFile}` : 'project:paw.toml', input.projectConfig?.profile),
    sourceValue(`user:${input.userConfigPath}`, input.userConfig?.profile),
    sourceValue('default', DEFAULT_PROFILE),
  ]);
  return validateProfileName(profile.value, profile.source).pipe(Effect.as(profile));
}

/** Resolves the backend target source and value, if configured. */
function resolveBackendTarget(input: {
  readonly rootOptions: RootOptions;
  readonly env: Readonly<Record<string, string | undefined>>;
  readonly projectFile: string | undefined;
  readonly projectConfig: TomlConfig | undefined;
  readonly profileConfig: TomlConfig | undefined;
  readonly profileConfigPath: string;
  readonly userConfig: TomlConfig | undefined;
  readonly userConfigPath: string;
}): SourceValue | undefined {
  return firstOptionalValue([
    sourceValue('flag', optionString(input.rootOptions.backendUrl)),
    sourceValue('env:PAW_BACKEND_URL', input.env.PAW_BACKEND_URL),
    sourceValue(
      input.projectFile ? `project:${input.projectFile}` : 'project:paw.toml',
      input.projectConfig?.backendUrl
    ),
    sourceValue(`profile:${input.profileConfigPath}`, input.profileConfig?.backendUrl),
    sourceValue(`user:${input.userConfigPath}`, input.userConfig?.backendUrl),
  ]);
}

/** Converts an optional CLI value to a non-empty string. */
function optionString(value: Option.Option<string>): string | undefined {
  return nonEmpty(Option.getOrUndefined(value));
}

/** Removes absent TOML fields so exact optional types stay honest. */
function compactTomlConfig(input: {
  readonly profile?: string | undefined;
  readonly backendUrl?: string | undefined;
}): TomlConfig {
  return {
    ...(input.profile ? { profile: input.profile } : {}),
    ...(input.backendUrl ? { backendUrl: input.backendUrl } : {}),
  };
}

/** Builds a sourced value when text is present. */
function sourceValue(source: string, value: string | undefined): SourceValue | undefined {
  const clean = nonEmpty(value);
  if (!clean) {
    return undefined;
  }
  return { source, value: clean };
}

/** Returns the first sourced value, falling back to the default profile. */
function firstValue(values: ReadonlyArray<SourceValue | undefined>): SourceValue {
  return firstOptionalValue(values) ?? { source: 'default', value: DEFAULT_PROFILE };
}

/** Returns the first present sourced value. */
function firstOptionalValue(values: ReadonlyArray<SourceValue | undefined>): SourceValue | undefined {
  return values.find((value) => value !== undefined);
}

/** Trims empty strings to undefined. */
function nonEmpty(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : undefined;
}

/** Returns true for plain object records. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Reads a string field from a record. */
function readString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  return typeof value === 'string' ? nonEmpty(value) : undefined;
}

/** Returns the first secret-looking nested path, if any. */
function findSecretPath(value: unknown, path: string): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  for (const [key, nested] of Object.entries(value)) {
    const nextPath = `${path}.${key}`;
    if (isSecretKey(key)) {
      return nextPath;
    }
    const nestedPath = findSecretPath(nested, nextPath);
    if (nestedPath) {
      return nestedPath;
    }
  }

  return undefined;
}

/** Returns true when a field name looks like auth or secret material. */
function isSecretKey(key: string): boolean {
  const normalized = key.toLowerCase().replaceAll('-', '_');
  return (
    normalized.includes('token') ||
    normalized.includes('secret') ||
    normalized.includes('cookie') ||
    normalized.includes('password') ||
    normalized.includes('api_key') ||
    normalized.includes('access_key') ||
    normalized.includes('private_key') ||
    normalized.includes('signing_key') ||
    normalized.includes('auth_key') ||
    normalized.includes('encryption_key') ||
    normalized === 'key'
  );
}

import {
  ConfigProvider,
  Context,
  Effect,
  Config as EffectConfig,
  FileSystem,
  Layer,
  Option,
  Path,
  Schema,
} from 'effect';
import { ActiveContext } from '../Infrastructure/ActiveContext';
import { validateNoSecrets } from './ConfigSecrets';
import type { PawCliError, UsageError } from './Errors';
import { ConfigError, UsageError as TaggedUsageError } from './Errors';
import type { RootOptions } from './Options';
import type { OptionalText, PersistedConfigRecord } from './Schemas';
import {
  decodeOptionalText,
  decodePersistedConfigRecord,
  normalizeTextOption,
  OptionalTrimmedText,
  OptionalTrimmedTextFromKey,
  optionToNullable,
  ProfileName,
} from './Schemas';

export { validateNoSecrets } from './ConfigSecrets';

export type ResolveContextOptions = {
  readonly rootOptions: RootOptions;
  readonly cwd: OptionalText;
};

export type ProfileConfigInput = {
  readonly profile: string;
  readonly configRoot: string;
  readonly values: Readonly<Record<string, string>>;
};

export type CliProcessShape = {
  readonly cwd: string;
  readonly env: Readonly<Record<string, string>>;
  readonly home: string;
};

export type EnvironmentOverrides = {
  readonly pawHome: OptionalText;
  readonly pawProfile: OptionalText;
  readonly pawBackendUrl: OptionalText;
  readonly xdgConfigHome: OptionalText;
  readonly xdgCacheHome: OptionalText;
};

type TomlConfig = {
  readonly profile: OptionalText;
  readonly backendUrl: OptionalText;
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
const PAW_HOME = 'PAW_HOME';
const PAW_PROFILE = 'PAW_PROFILE';
const PAW_BACKEND_URL = 'PAW_BACKEND_URL';
const XDG_CONFIG_HOME = 'XDG_CONFIG_HOME';
const XDG_CACHE_HOME = 'XDG_CACHE_HOME';

const tomlConfigInputSchema = Schema.Struct({
  profile: OptionalTrimmedTextFromKey,
  backend_url: OptionalTrimmedTextFromKey,
  backendUrl: OptionalTrimmedTextFromKey,
}).pipe(
  Schema.annotate({
    identifier: 'PawCliTomlConfig',
    title: 'Paw CLI TOML Config',
    description: 'Supported config keys decoded from Paw CLI TOML files.',
  })
);

const environmentOverridesConfig = EffectConfig.all({
  pawHome: optionalEnvText(PAW_HOME),
  pawProfile: optionalEnvText(PAW_PROFILE),
  pawBackendUrl: optionalEnvText(PAW_BACKEND_URL),
  xdgConfigHome: optionalEnvText(XDG_CONFIG_HOME),
  xdgCacheHome: optionalEnvText(XDG_CACHE_HOME),
});

/** Provides process-level facts that the Bun entrypoint reads once. */
export class CliProcess extends Context.Service<CliProcess, CliProcessShape>()('@pawrrtal/cli/Process') {}

/** Provides Bun process facts as an Effect layer. */
export const CliProcessLive: Layer.Layer<CliProcess> = Layer.sync(CliProcess, () => ({
  cwd: process.cwd(),
  env: processEnvironment(Bun.env),
  // biome-ignore lint/complexity/useLiteralKeys: TS noPropertyAccessFromIndexSignature requires bracket access.
  home: Bun.env['HOME'] ?? Bun.env['USERPROFILE'] ?? '/tmp',
}));

/**
 * Resolves the active Paw CLI context from flags, environment, and TOML files.
 *
 * @param options - Root command options and working directory override.
 * @returns Active context with source metadata and no secret values.
 */
export function resolveActiveContext(
  options: ResolveContextOptions
): Effect.Effect<ActiveContext, PawCliError, CliProcess | FileSystem.FileSystem | Path.Path> {
  return Effect.gen(function* () {
    const processInfo = yield* CliProcess;
    const pathService = yield* Path.Path;
    const cwd = pathService.resolve(Option.getOrElse(options.cwd, () => processInfo.cwd));
    const environment = yield* readEnvironmentOverrides(processInfo.env);
    const stateRoots = resolveStateRoots({ environment, home: processInfo.home, path: pathService });
    const projectFile = yield* findUp(cwd, PROJECT_CONFIG_FILE);
    const projectConfig = yield* readTomlConfig(projectFile);
    const userConfigPath = pathService.join(stateRoots.configRoot, CONFIG_FILE);
    const userConfig = yield* readTomlConfig(Option.some(userConfigPath));
    const profile = yield* resolveProfile({
      rootOptions: options.rootOptions,
      environment,
      projectFile,
      projectConfig,
      userConfig,
      userConfigPath,
    });
    const profileConfigPath = pathService.join(stateRoots.configRoot, PROFILE_DIR, `${profile.value}.toml`);
    const profileConfig = yield* readTomlConfig(Option.some(profileConfigPath));
    const backendTarget = resolveBackendTarget({
      rootOptions: options.rootOptions,
      environment,
      projectFile,
      projectConfig,
      profileConfig,
      profileConfigPath,
      userConfig,
      userConfigPath,
    });

    return yield* Schema.decodeUnknownEffect(ActiveContext)({
      profile: profile.value,
      configRoot: stateRoots.configRoot,
      cacheRoot: stateRoots.cacheRoot,
      backendTarget: optionToNullable(Option.map(backendTarget, (target) => target.value)),
      backendTargetSource: optionToNullable(Option.map(backendTarget, (target) => target.source)),
      backendTargetUnsetReason: Option.isSome(backendTarget) ? null : 'No backend target configured.',
      authState: 'not_applicable',
      configSources: [
        { key: 'profile', source: profile.source, value: profile.value },
        {
          key: 'backendTarget',
          source: Option.match(backendTarget, { onNone: () => 'unset', onSome: (target) => target.source }),
          value: optionToNullable(Option.map(backendTarget, (target) => target.value)),
        },
        { key: 'configRoot', source: stateRoots.configSource, value: stateRoots.configRoot },
        { key: 'cacheRoot', source: stateRoots.cacheSource, value: stateRoots.cacheRoot },
      ],
    }).pipe(
      Effect.mapError(
        (schemaError) =>
          new ConfigError({
            message: 'Resolved active context did not match its public schema.',
            details: String(schemaError),
          })
      )
    );
  });
}

/**
 * Decodes environment overrides with Effect Config against a supplied provider.
 *
 * @param env - Environment map to decode.
 * @returns Supported Paw CLI environment overrides.
 */
export function readEnvironmentOverrides(
  env: Readonly<Record<string, string>>
): Effect.Effect<EnvironmentOverrides, ConfigError> {
  const provider = ConfigProvider.fromEnv({ env });
  return environmentOverridesConfig.parse(provider).pipe(
    Effect.mapError(
      (error) =>
        new ConfigError({
          message: 'Could not decode Paw CLI environment overrides.',
          details: String(error),
        })
    )
  );
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
          (error) => new ConfigError({ message: 'Could not create profile config directory.', details: String(error) })
        )
      );

    const filePath = pathService.join(profileDir, `${profile}.toml`);
    const body = Object.entries(input.values)
      .flatMap(([key, value]) =>
        Option.match(decodeOptionalText(value), {
          onNone: () => [],
          onSome: (text) => [`${key} = ${JSON.stringify(text)}`],
        })
      )
      .join('\n');

    yield* fs
      .writeFileString(filePath, `${body}\n`)
      .pipe(
        Effect.mapError(
          (error) => new ConfigError({ message: 'Could not write profile config.', details: String(error) })
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
  return Schema.decodeUnknownEffect(ProfileName)(value).pipe(
    Effect.mapError(
      () =>
        new TaggedUsageError({
          message: `Invalid profile name '${value}'.`,
          hint: 'Start with a letter or number, then use letters, numbers, dot, dash, or underscore.',
          details: `Profile source: ${source}`,
        })
    )
  );
}

/** Resolves state roots from Paw and XDG environment variables. */
function resolveStateRoots(input: {
  readonly environment: EnvironmentOverrides;
  readonly home: string;
  readonly path: Path.Path;
}): StateRoots {
  const { environment, home, path } = input;
  if (Option.isSome(environment.pawHome)) {
    const root = path.resolve(environment.pawHome.value);
    return {
      configRoot: path.join(root, 'config'),
      cacheRoot: path.join(root, 'cache'),
      configSource: 'env:PAW_HOME',
      cacheSource: 'env:PAW_HOME',
    };
  }

  const configBase = Option.match(environment.xdgConfigHome, {
    onNone: () => path.join(home, '.config'),
    onSome: (root) => path.resolve(root),
  });
  const cacheBase = Option.match(environment.xdgCacheHome, {
    onNone: () => path.join(home, '.cache'),
    onSome: (root) => path.resolve(root),
  });

  return {
    configRoot: path.join(configBase, 'pawrrtal'),
    cacheRoot: path.join(cacheBase, 'pawrrtal'),
    configSource: Option.isSome(environment.xdgConfigHome) ? 'env:XDG_CONFIG_HOME' : 'home-default',
    cacheSource: Option.isSome(environment.xdgCacheHome) ? 'env:XDG_CACHE_HOME' : 'home-default',
  };
}

/** Reads a TOML config file when the path exists. */
function readTomlConfig(
  filePath: OptionalText
): Effect.Effect<Option.Option<TomlConfig>, ConfigError, FileSystem.FileSystem> {
  if (Option.isNone(filePath)) {
    return Effect.succeed(Option.none());
  }

  return Effect.gen(function* () {
    const fs = yield* FileSystem.FileSystem;
    const exists = yield* fs.exists(filePath.value).pipe(Effect.orElseSucceed(() => false));
    if (!exists) {
      return Option.none();
    }

    const source = yield* fs
      .readFileString(filePath.value)
      .pipe(
        Effect.mapError(
          (error) => new ConfigError({ message: `Could not read ${filePath.value}.`, details: String(error) })
        )
      );
    return Option.some(yield* parseTomlConfig(source, filePath.value));
  });
}

/** Parses supported Paw TOML keys from file content. */
function parseTomlConfig(source: string, filePath: string): Effect.Effect<TomlConfig, ConfigError> {
  return Effect.gen(function* () {
    const parsedToml = yield* Effect.try({
      try: () => Bun.TOML.parse(source),
      catch: (error) => new ConfigError({ message: `Could not parse ${filePath}.`, details: String(error) }),
    });
    const persistedConfig = yield* decodePersistedConfigRecord(parsedToml, filePath);
    yield* validateNoSecrets(persistedConfig, filePath);
    return yield* decodeTomlConfigInput(persistedConfig, filePath);
  });
}

/** Decodes supported TOML fields from parsed Bun TOML output. */
function decodeTomlConfigInput(value: PersistedConfigRecord, filePath: string): Effect.Effect<TomlConfig, ConfigError> {
  return Schema.decodeUnknownEffect(tomlConfigInputSchema)(value).pipe(
    Effect.map((decoded) => ({
      profile: decoded.profile,
      backendUrl: Option.firstSomeOf([decoded.backend_url, decoded.backendUrl]),
    })),
    Effect.mapError(
      (schemaError) =>
        new ConfigError({
          message: `Could not decode ${filePath}.`,
          details: String(schemaError),
        })
    )
  );
}

/** Finds a file by walking from a directory to the filesystem root. */
function findUp(
  startDirectory: string,
  fileName: string
): Effect.Effect<OptionalText, never, FileSystem.FileSystem | Path.Path> {
  return Effect.gen(function* () {
    const fs = yield* FileSystem.FileSystem;
    const pathService = yield* Path.Path;
    let current = startDirectory;
    while (true) {
      const candidate = pathService.join(current, fileName);
      const exists = yield* fs.exists(candidate).pipe(Effect.orElseSucceed(() => false));
      if (exists) {
        return Option.some(candidate);
      }

      const parent = pathService.dirname(current);
      if (parent === current || pathService.parse(current).root === current) {
        return Option.none();
      }
      current = parent;
    }
  });
}

/** Resolves the active profile source and value. */
function resolveProfile(input: {
  readonly rootOptions: RootOptions;
  readonly environment: EnvironmentOverrides;
  readonly projectFile: OptionalText;
  readonly projectConfig: Option.Option<TomlConfig>;
  readonly userConfig: Option.Option<TomlConfig>;
  readonly userConfigPath: string;
}): Effect.Effect<SourceValue, UsageError> {
  const profile = firstValue([
    sourceValue('flag', normalizeTextOption(input.rootOptions.profile)),
    sourceValue('env:PAW_PROFILE', input.environment.pawProfile),
    sourceValue(
      projectSource(input.projectFile),
      Option.flatMap(input.projectConfig, (config) => config.profile)
    ),
    sourceValue(
      `user:${input.userConfigPath}`,
      Option.flatMap(input.userConfig, (config) => config.profile)
    ),
    sourceValue('default', Option.some(DEFAULT_PROFILE)),
  ]);
  return validateProfileName(profile.value, profile.source).pipe(Effect.as(profile));
}

/** Resolves the backend target source and value, if configured. */
function resolveBackendTarget(input: {
  readonly rootOptions: RootOptions;
  readonly environment: EnvironmentOverrides;
  readonly projectFile: OptionalText;
  readonly projectConfig: Option.Option<TomlConfig>;
  readonly profileConfig: Option.Option<TomlConfig>;
  readonly profileConfigPath: string;
  readonly userConfig: Option.Option<TomlConfig>;
  readonly userConfigPath: string;
}): Option.Option<SourceValue> {
  return firstOptionalValue([
    sourceValue('flag', normalizeTextOption(input.rootOptions.backendUrl)),
    sourceValue('env:PAW_BACKEND_URL', input.environment.pawBackendUrl),
    sourceValue(
      projectSource(input.projectFile),
      Option.flatMap(input.projectConfig, (config) => config.backendUrl)
    ),
    sourceValue(
      `profile:${input.profileConfigPath}`,
      Option.flatMap(input.profileConfig, (config) => config.backendUrl)
    ),
    sourceValue(
      `user:${input.userConfigPath}`,
      Option.flatMap(input.userConfig, (config) => config.backendUrl)
    ),
  ]);
}

/** Builds an optional environment config descriptor. */
function optionalEnvText(name: string): EffectConfig.Config<OptionalText> {
  return EffectConfig.schema(OptionalTrimmedText, name).pipe(EffectConfig.withDefault(Option.none()));
}

/** Returns the source label for the project config path. */
function projectSource(projectFile: OptionalText): string {
  return Option.match(projectFile, {
    onNone: () => 'project:paw.toml',
    onSome: (filePath) => `project:${filePath}`,
  });
}

/** Builds a sourced value when text is present. */
function sourceValue(source: string, value: OptionalText): Option.Option<SourceValue> {
  return Option.map(value, (text) => ({ source, value: text }));
}

/** Returns the first sourced value, falling back to the default profile. */
function firstValue(values: ReadonlyArray<Option.Option<SourceValue>>): SourceValue {
  return Option.getOrElse(firstOptionalValue(values), () => ({ source: 'default', value: DEFAULT_PROFILE }));
}

/** Returns the first present sourced value. */
function firstOptionalValue(values: ReadonlyArray<Option.Option<SourceValue>>): Option.Option<SourceValue> {
  return Option.firstSomeOf(values);
}

/** Converts a Bun environment object to a plain string map. */
function processEnvironment(env: typeof Bun.env): Readonly<Record<string, string>> {
  return Object.fromEntries(
    Object.entries(env).flatMap(([key, value]) => (typeof value === 'string' ? [[key, value] as const] : []))
  );
}

import { Effect } from 'effect';
import type { Command } from 'effect/unstable/cli';
import type { CommandMetadata } from './Helpers/CommandMetadata';
import { makeRootMetadata } from './Helpers/CommandMetadata';
import type { UsageError } from './Helpers/Errors';
import { failUsage } from './Helpers/Errors';
import { COMPLETIONS_METADATA, makeCompletionsCommand } from './Modules/Completions/Command';
import { ContextCommand } from './Modules/Context/Command';
import { DoctorCommand } from './Modules/Doctor/Command';

export type RegisteredCommandModule = {
  readonly command: Command.Command.Any;
  readonly metadata: CommandMetadata;
};

export type CommandRegistry = {
  readonly modules: ReadonlyArray<RegisteredCommandModule>;
  readonly rootMetadata: ReturnType<typeof makeRootMetadata>;
};

type RuntimeCommandModule = typeof DoctorCommand | typeof ContextCommand;
export type RuntimeCommandRegistry = {
  readonly modules: ReadonlyArray<RuntimeCommandModule | ReturnType<typeof makeCompletionsCommand>>;
  readonly rootMetadata: ReturnType<typeof makeRootMetadata>;
};

type CommandRegistryLike = {
  readonly modules: ReadonlyArray<{
    readonly metadata: CommandMetadata;
  }>;
};

const BASE_COMMANDS = [DoctorCommand, ContextCommand] as const satisfies ReadonlyArray<RuntimeCommandModule>;

/** Default command registry used by the Bun entrypoint. */
export const DefaultCommandRegistry = makeRuntimeCommandRegistry(BASE_COMMANDS);

/**
 * Builds a command registry from feature-owned command modules.
 *
 * @param modules - Command modules to expose under `paw`.
 * @returns Registry with executable modules and root metadata.
 */
export function makeCommandRegistry(modules: ReadonlyArray<RegisteredCommandModule>): CommandRegistry {
  const rootMetadata = makeRootMetadata([...modules.map((module) => module.metadata), COMPLETIONS_METADATA]);
  return {
    modules: [...modules, makeCompletionsCommand(rootMetadata)],
    rootMetadata,
  };
}

/**
 * Validates that command names and aliases are unique.
 *
 * @param registry - Command registry to inspect.
 * @returns The same registry when no duplicate command name exists.
 */
export function validateCommandRegistry<Registry extends CommandRegistryLike>(
  registry: Registry
): Effect.Effect<Registry, UsageError> {
  const seen = new Set<string>();
  for (const module of registry.modules) {
    const metadata: CommandMetadata = module.metadata;
    const names = [metadata.name, ...(metadata.aliases ?? [])];
    for (const name of names) {
      if (seen.has(name)) {
        return failUsage(`Command name or alias '${name}' is registered more than once.`);
      }
      seen.add(name);
    }
  }
  return Effect.succeed(registry);
}

/** Builds the typed runtime registry used by the executable root command. */
function makeRuntimeCommandRegistry(modules: ReadonlyArray<RuntimeCommandModule>): RuntimeCommandRegistry {
  const rootMetadata = makeRootMetadata([...modules.map((module) => module.metadata), COMPLETIONS_METADATA]);
  return {
    modules: [...modules, makeCompletionsCommand(rootMetadata)],
    rootMetadata,
  };
}

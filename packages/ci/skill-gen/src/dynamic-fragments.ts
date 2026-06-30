import { access } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import type { ParsedSkillFragment } from './parse';

type DynamicSkillFragment = {
  readonly name: string;
  readonly description: string;
  readonly extraFrontmatter?: ReadonlyArray<string>;
  readonly body: string;
  readonly relativePath?: string;
};

type DynamicFragmentModule = {
  readonly getSkillFragments?: () => ReadonlyArray<DynamicSkillFragment> | Promise<ReadonlyArray<DynamicSkillFragment>>;
};

const DYNAMIC_FRAGMENT_MODULES = ['packages/paw-cli/src/Skills/Fragments.ts'] as const;

/**
 * Loads generated skill fragments from registered dynamic sources.
 *
 * @param baseDir - Repository root or fixture root used by the current run.
 * @param verbose - When true, logs each dynamic source that contributed fragments.
 * @returns Parsed fragments ready to merge with marker-scanned fragments.
 */
export async function loadDynamicFragments(baseDir: string, verbose = false): Promise<ParsedSkillFragment[]> {
  const fragments: ParsedSkillFragment[] = [];

  for (const source of DYNAMIC_FRAGMENT_MODULES) {
    const modulePath = resolve(baseDir, source);
    if (!(await pathExists(modulePath))) {
      continue;
    }

    const loaded = await importDynamicModule(modulePath);
    const sourceFragments = await loadSourceFragments(loaded, source);
    fragments.push(...sourceFragments.map((fragment) => normalizeFragment(fragment, source)));

    if (verbose) {
      process.stdout.write(`dynamic-fragments: loaded ${sourceFragments.length} fragment(s) from ${source}\n`);
    }
  }

  return fragments.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
}

/** Returns true when a dynamic source exists on disk. */
async function pathExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

/** Imports one dynamic fragment module. */
async function importDynamicModule(modulePath: string): Promise<DynamicFragmentModule> {
  return (await import(pathToFileURL(modulePath).href)) as DynamicFragmentModule;
}

/** Loads fragments from one module export. */
async function loadSourceFragments(
  module: DynamicFragmentModule,
  sourcePath: string
): Promise<ReadonlyArray<DynamicSkillFragment>> {
  if (!module.getSkillFragments) {
    throw new Error(`Dynamic skill source ${sourcePath} must export getSkillFragments().`);
  }

  return module.getSkillFragments();
}

/** Normalizes a dynamic fragment into the parsed fragment model. */
function normalizeFragment(fragment: DynamicSkillFragment, sourcePath: string): ParsedSkillFragment {
  if (fragment.name.length === 0 || fragment.description.length === 0) {
    throw new Error(`Dynamic skill source ${sourcePath} returned a fragment without name or description.`);
  }

  return {
    name: fragment.name,
    description: fragment.description,
    extraFrontmatter: [...(fragment.extraFrontmatter ?? [])],
    body: fragment.body,
    relativePath: fragment.relativePath ?? sourcePath,
  };
}

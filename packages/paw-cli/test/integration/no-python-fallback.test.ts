import { describe, expect, it } from 'vitest';
import { pathJoin, REPO_ROOT, readTextFileIfExists } from './harness';

const FORBIDDEN_REFERENCES = [
  'app.cli.paw',
  'uv run paw',
  'backend/app/cli/paw',
  'backend/tests/paw',
  'paw-extend',
] as const;

describe('old Python CLI fallback removal', (): void => {
  it('keeps supported launcher and generated-skill surfaces off the Python Paw CLI', async (): Promise<void> => {
    const combined = await readRepoFiles([
      'scripts/paw',
      'justfile',
      'backend/pyproject.toml',
      '.agent/skills/paw/SKILL.md',
      '.agent/skills/domain-cli/SKILL.md',
    ]);

    for (const reference of FORBIDDEN_REFERENCES) {
      expect(combined).not.toContain(reference);
    }
  });
});

/** Reads repo files that exist and concatenates their contents. */
async function readRepoFiles(paths: ReadonlyArray<string>): Promise<string> {
  const contents = await Promise.all(paths.map(readRepoFileIfExists));
  return contents.join('\n');
}

/** Reads one repo file, returning empty text when it is absent. */
async function readRepoFileIfExists(path: string): Promise<string> {
  return readTextFileIfExists(pathJoin(REPO_ROOT, path));
}

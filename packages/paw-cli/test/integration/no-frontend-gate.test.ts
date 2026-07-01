import { describe, expect, it } from 'vitest';
import { pathJoin, REPO_ROOT, readTextFileIfExists } from './harness';

const FRONTEND_GATE_TOKENS = [
  'frontend',
  'next',
  'playwright',
  'stagehand',
  'design:lint',
  'test-frontend',
  'arch-fe',
] as const;

describe('focused CLI gate', (): void => {
  it('keeps the just recipe off frontend and browser gates', async (): Promise<void> => {
    const justfile = await readRepoText('justfile');
    const recipe = extractRecipeBody({ name: 'paw-cli-check', justfile });

    expect(recipe).toContain("bun run --filter '@pawrrtal/cli' check");
    expect(recipe).toContain('bun run skill-gen:check');
    for (const token of FRONTEND_GATE_TOKENS) {
      expect(recipe).not.toContain(token);
    }
  });

  it('keeps the repo launcher pointed at the Bun CLI package', async (): Promise<void> => {
    const launcher = await readRepoText('scripts/paw');

    expect(launcher).toContain('packages/paw-cli/src/Main.ts');
    expect(launcher).toContain('exec bun run');
    expect(launcher).not.toContain('uv run paw');
    for (const token of FRONTEND_GATE_TOKENS) {
      expect(launcher).not.toContain(token);
    }
  });
});

/** Reads text from a repo-relative path. */
async function readRepoText(path: string): Promise<string> {
  const text = await readTextFileIfExists(pathJoin(REPO_ROOT, path));
  if (text.length === 0) {
    throw new Error(`Missing repo file: ${path}`);
  }

  return text;
}

/** Extracts one just recipe body by name. */
function extractRecipeBody(input: { readonly name: string; readonly justfile: string }): string {
  const lines = input.justfile.split('\n');
  const recipeStart = lines.findIndex((line) => line.trim() === `${input.name}:`);
  if (recipeStart < 0) {
    throw new Error(`Missing just recipe: ${input.name}`);
  }

  const body: string[] = [];
  for (const line of lines.slice(recipeStart + 1)) {
    if (!isRecipeBodyLine(line)) {
      break;
    }
    body.push(line);
  }

  return body.join('\n');
}

/** Returns true when a justfile line belongs to the current recipe body. */
function isRecipeBodyLine(line: string): boolean {
  return line.startsWith(' ') || line.startsWith('\t') || line.trim().length === 0;
}

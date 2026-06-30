import { describe, expect, it } from 'vitest';
import { pathJoin, REPO_ROOT, readTextFileIfExists } from './harness';

type PackageScripts = Readonly<Record<string, string | undefined>>;

type PackageJson = {
  readonly scripts?: PackageScripts;
};

const FRONTEND_GATE_TOKENS = ['frontend', 'next', 'playwright', 'stagehand', 'design:lint', 'dev-console'] as const;

describe('package check script', (): void => {
  it('keeps package check scoped to CLI typecheck and tests', async (): Promise<void> => {
    const scripts = await readCliPackageScripts();
    const checkScript = requiredScript(scripts, 'check');

    expect(checkScript).toBe('bun run typecheck && bun run test');
    for (const token of FRONTEND_GATE_TOKENS) {
      expect(checkScript).not.toContain(token);
    }
  });

  it('runs Vitest with the Bun runtime', async (): Promise<void> => {
    const scripts = await readCliPackageScripts();

    expect(requiredScript(scripts, 'test')).toBe('bun --bun vitest run');
  });
});

/** Reads the CLI package scripts from package.json. */
async function readCliPackageScripts(): Promise<PackageScripts> {
  const text = await readTextFileIfExists(pathJoin(REPO_ROOT, 'packages/paw-cli/package.json'));
  const manifest = JSON.parse(text) as PackageJson;
  return manifest.scripts ?? {};
}

/** Returns a required package script. */
function requiredScript(scripts: PackageScripts, name: string): string {
  const script = scripts[name];
  if (!script) {
    throw new Error(`Missing package script: ${name}`);
  }

  return script;
}

import { describe, expect, it } from 'vitest';
import { makeTempDirectory, pathJoin, runCli, writeTextFile } from './harness';

describe('config resolution', (): void => {
  it('uses PAW_HOME for config and cache roots', async (): Promise<void> => {
    const root = await makeTempRoot();
    const result = await runCli({
      args: ['context', '--json'],
      cwd: root,
      env: { HOME: pathJoin(root, 'home'), PAW_HOME: root },
    });

    const context = JSON.parse(result.stdout) as {
      readonly configRoot: string;
      readonly cacheRoot: string;
    };

    expect(result.exitCode).toBe(0);
    expect(context.configRoot).toBe(pathJoin(root, 'config'));
    expect(context.cacheRoot).toBe(pathJoin(root, 'cache'));
  });

  it('prefers flag values over environment and TOML config', async (): Promise<void> => {
    const root = await makeTempRoot();
    const workspace = pathJoin(root, 'workspace');
    await writeTextFile(pathJoin(workspace, 'paw.toml'), 'profile = "project"\nbackend_url = "http://project"\n');

    const result = await runCli({
      args: ['--profile', 'flag', '--backend-url', 'http://flag', 'context', '--json'],
      cwd: workspace,
      env: { HOME: pathJoin(root, 'home'), PAW_BACKEND_URL: 'http://env', PAW_HOME: root, PAW_PROFILE: 'env' },
    });

    const context = JSON.parse(result.stdout) as {
      readonly backendTarget: string;
      readonly configSources: ReadonlyArray<{ readonly key: string; readonly source: string }>;
      readonly profile: string;
    };

    expect(result.exitCode).toBe(0);
    expect(context.profile).toBe('flag');
    expect(context.backendTarget).toBe('http://flag');
    expect(context.configSources.find((source) => source.key === 'profile')?.source).toBe('flag');
  });

  it('treats empty environment strings as unset', async (): Promise<void> => {
    const root = await makeTempRoot();
    const result = await runCli({
      args: ['context', '--json'],
      cwd: root,
      env: { HOME: pathJoin(root, 'home'), PAW_BACKEND_URL: '', PAW_HOME: root, PAW_PROFILE: '   ' },
    });

    const context = JSON.parse(result.stdout) as {
      readonly backendTarget: string | null;
      readonly profile: string;
    };

    expect(result.exitCode).toBe(0);
    expect(context.profile).toBe('default');
    expect(context.backendTarget).toBeNull();
  });
});

/** Creates one temporary root for config integration tests. */
function makeTempRoot(): Promise<string> {
  return makeTempDirectory('paw-cli-config');
}

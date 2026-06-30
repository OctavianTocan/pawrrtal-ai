import { describe, expect, it } from 'vitest';
import { makeTempDirectory, pathJoin, runCli, runLauncher, writeTextFile } from './harness';

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

  it('rejects profile names that can escape the profile directory', async (): Promise<void> => {
    const root = await makeTempRoot();
    const result = await runCli({
      args: ['--profile', '../outside', 'context', '--json'],
      cwd: root,
      env: { HOME: pathJoin(root, 'home'), PAW_HOME: root },
    });

    expect(result.exitCode).toBe(2);
    expect(result.stdout).toBe('');
    expect(result.stderr).toContain('Invalid profile name');
    expect(result.stderr).not.toContain('causePrettyError');
  });

  it('rejects traversal profile names from project TOML', async (): Promise<void> => {
    const root = await makeTempRoot();
    const workspace = pathJoin(root, 'workspace');
    await writeTextFile(pathJoin(workspace, 'paw.toml'), 'profile = "../outside"\n');

    const result = await runCli({
      args: ['context', '--json'],
      cwd: workspace,
      env: { HOME: pathJoin(root, 'home'), PAW_HOME: root },
    });

    expect(result.exitCode).toBe(2);
    expect(result.stdout).toBe('');
    expect(result.stderr).toContain('Invalid profile name');
  });

  it('rejects profile names that start with a dash', async (): Promise<void> => {
    const root = await makeTempRoot();
    const result = await runCli({
      args: ['context', '--json'],
      cwd: root,
      env: { HOME: pathJoin(root, 'home'), PAW_HOME: root, PAW_PROFILE: '-bad' },
    });

    expect(result.exitCode).toBe(2);
    expect(result.stdout).toBe('');
    expect(result.stderr).toContain('Invalid profile name');
  });

  it('preserves caller cwd when running through scripts/paw', async (): Promise<void> => {
    const root = await makeTempRoot();
    const workspace = pathJoin(root, 'workspace');
    await writeTextFile(pathJoin(workspace, 'paw.toml'), 'profile = "project"\nbackend_url = "http://project"\n');

    const result = await runLauncher({
      args: ['context', '--json'],
      cwd: workspace,
      env: { HOME: pathJoin(root, 'home'), PAW_HOME: root },
    });

    const context = JSON.parse(result.stdout) as {
      readonly backendTarget: string;
      readonly profile: string;
    };

    expect(result.exitCode).toBe(0);
    expect(context.profile).toBe('project');
    expect(context.backendTarget).toBe('http://project');
  });
});

/** Creates one temporary root for config integration tests. */
function makeTempRoot(): Promise<string> {
  return makeTempDirectory('paw-cli-config');
}

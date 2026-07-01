import { describe, expect, it } from 'vitest';
import { runCli } from './harness';

describe('context command', (): void => {
  it('prints active context as JSON without secrets', async (): Promise<void> => {
    const result = await runCli({
      args: ['--profile', 'local', '--backend-url', 'http://localhost:8000', 'context', '--json'],
      env: { PAW_HOME: `/tmp/paw-cli-context-${crypto.randomUUID()}` },
    });

    expect(result.exitCode).toBe(0);
    expect(result.stderr).toBe('');
    expect(JSON.parse(result.stdout)).toMatchObject({
      authState: 'not_applicable',
      backendTarget: 'http://localhost:8000',
      profile: 'local',
    });
    expect(result.stdout.toLowerCase()).not.toContain('token');
  });

  it('supports whoami as the context alias', async (): Promise<void> => {
    const result = await runCli({
      args: ['whoami', '--plain'],
      env: { PAW_HOME: `/tmp/paw-cli-whoami-${crypto.randomUUID()}` },
    });

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain('default');
  });
});

import { describe, expect, it } from 'vitest';
import { runCli } from './harness';

describe('doctor command', (): void => {
  it('prints local health as JSON', async (): Promise<void> => {
    const result = await runCli({
      args: ['doctor', '--json'],
      env: { PAW_HOME: `/tmp/paw-cli-doctor-${crypto.randomUUID()}` },
    });

    const report = JSON.parse(result.stdout) as {
      readonly status: string;
      readonly checks: ReadonlyArray<{ readonly name: string; readonly status: string }>;
    };

    expect(result.exitCode).toBe(0);
    expect(report.status).toMatch(/pass|warn/);
    expect(report.checks.map((check) => check.name)).toContain('cli-package-version');
    expect(report.checks.map((check) => check.name)).toContain('active-profile');
  });

  it('prints one plain row per check', async (): Promise<void> => {
    const result = await runCli({
      args: ['doctor', '--plain'],
      env: { PAW_HOME: `/tmp/paw-cli-doctor-plain-${crypto.randomUUID()}` },
    });

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain('cli-package-version\tpass\t0.1.0');
  });
});

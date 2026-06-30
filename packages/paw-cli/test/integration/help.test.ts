import { describe, expect, it } from 'vitest';
import { runCli } from './harness';

describe('root help and version', (): void => {
  it('prints the supported root command surface', async (): Promise<void> => {
    const result = await runCli({ args: ['--help'] });

    expect(result.exitCode).toBe(0);
    expect(result.stderr).toBe('');
    expect(result.stdout).toContain('paw <command> [options]');
    expect(result.stdout).toContain('doctor');
    expect(result.stdout).toContain('context, whoami');
    expect(result.stdout).not.toContain('verify chat-roundtrip');
  });

  it('prints version with -V and keeps -v for verbose mode', async (): Promise<void> => {
    const version = await runCli({ args: ['-V'] });
    const verboseDoctor = await runCli({ args: ['-v', 'doctor', '--json'] });

    expect(version.exitCode).toBe(0);
    expect(version.stdout.trim()).toBe('paw v0.1.0');
    expect(verboseDoctor.exitCode).toBe(0);
    expect(verboseDoctor.stdout).toContain('"status"');
  });
});

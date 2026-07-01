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

  it('prints root help when no subcommand is supplied', async (): Promise<void> => {
    const result = await runCli({ args: [] });

    expect(result.exitCode).toBe(0);
    expect(result.stderr).toBe('');
    expect(result.stdout).toContain('paw <command> [options]');
    expect(result.stdout).toContain('doctor');
  });

  it('prints root help when help is requested with root option values', async (): Promise<void> => {
    const result = await runCli({ args: ['--profile', 'doctor', '--help'] });

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain('paw <command> [options]');
    expect(result.stdout).toContain('--profile string');
    expect(result.stdout).not.toContain('paw doctor [options]');
  });

  it('prints version with -V and keeps -v for verbose mode', async (): Promise<void> => {
    const version = await runCli({ args: ['-V'] });
    const verboseDoctor = await runCli({ args: ['-v', 'doctor', '--json'] });

    expect(version.exitCode).toBe(0);
    expect(version.stdout.trim()).toBe('paw v0.1.0');
    expect(verboseDoctor.exitCode).toBe(0);
    expect(verboseDoctor.stdout).toContain('"status"');
  });

  it('does not let help or version flags mask an invalid command', async (): Promise<void> => {
    const helpResult = await runCli({ args: ['not-a-command', '--help'] });
    const versionResult = await runCli({ args: ['not-a-command', '--version'] });

    expect(helpResult.exitCode).toBe(2);
    expect(helpResult.stderr).toContain('Unknown subcommand');
    expect(helpResult.stdout).not.toContain('SUMMARY\n  Operate Pawrrtal');

    expect(versionResult.exitCode).toBe(2);
    expect(versionResult.stderr).toContain('version flag is only available at the root');
    expect(versionResult.stdout.trim()).not.toBe('paw v0.1.0');
  });
});

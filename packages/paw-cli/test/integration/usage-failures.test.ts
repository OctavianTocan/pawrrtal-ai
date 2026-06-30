import { describe, expect, it } from 'vitest';
import { runCli } from './harness';

describe('usage failure handling', (): void => {
  it('returns usage exit code for missing completion shell', async (): Promise<void> => {
    const result = await runCli({ args: ['completions'] });

    expect(result.exitCode).toBe(2);
    expect(result.stderr).toContain('Missing required argument: shell');
    expect(result.stdout).not.toContain('--version, -v');
    expect(result.stderr).not.toContain('Error: Help requested');
    expect(result.stderr).not.toContain('causePrettyError');
  });

  it('returns usage exit code for unknown completion shell', async (): Promise<void> => {
    const result = await runCli({ args: ['completions', 'fish'] });

    expect(result.exitCode).toBe(2);
    expect(result.stderr).toContain('Invalid value for argument <shell>');
    expect(result.stdout).not.toContain('--version, -v');
    expect(result.stderr).not.toContain('causePrettyError');
  });

  it('returns usage exit code for conflicting output modes without a fiber trace', async (): Promise<void> => {
    const result = await runCli({ args: ['doctor', '--json', '--plain'] });

    expect(result.exitCode).toBe(2);
    expect(result.stdout).toBe('');
    expect(result.stderr).toContain('Choose only one output mode.');
    expect(result.stderr).not.toContain('causePrettyError');
  });

  it('renders verbose details only when requested', async (): Promise<void> => {
    const normal = await runCli({ args: ['--profile', '../outside', 'context'] });
    const verbose = await runCli({ args: ['--verbose', '--profile', '../outside', 'context'] });

    expect(normal.exitCode).toBe(2);
    expect(normal.stderr).toContain('Invalid profile name');
    expect(normal.stderr).not.toContain('Details:');

    expect(verbose.exitCode).toBe(2);
    expect(verbose.stderr).toContain('Invalid profile name');
    expect(verbose.stderr).toContain('Details:');
  });
});

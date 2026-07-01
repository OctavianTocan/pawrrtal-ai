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

  it('returns usage exit code for unsupported completion shell', async (): Promise<void> => {
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

  it('renders expected failures as structured stderr when JSON was requested', async (): Promise<void> => {
    const result = await runCli({ args: ['context', '--json', '--plain'] });
    const payload = JSON.parse(result.stderr) as {
      readonly error: {
        readonly kind: string;
        readonly message: string;
        readonly hint: string | null;
        readonly details: string | null;
      };
    };

    expect(result.exitCode).toBe(2);
    expect(result.stdout).toBe('');
    expect(payload.error.kind).toBe('usage');
    expect(payload.error.message).toBe('Choose only one output mode.');
    expect(payload.error.hint).toBe('Use either --json or --plain, not both.');
    expect(payload.error.details).toBeNull();
  });

  it('adds verbose details to structured stderr only when verbose diagnostics are requested', async (): Promise<void> => {
    const normal = await runCli({ args: ['--profile', '../outside', 'context', '--json'] });
    const verbose = await runCli({ args: ['--verbose', '--profile', '../outside', 'context', '--json'] });

    const normalPayload = JSON.parse(normal.stderr) as { readonly error: { readonly details: string | null } };
    const verbosePayload = JSON.parse(verbose.stderr) as { readonly error: { readonly details: string | null } };

    expect(normal.exitCode).toBe(2);
    expect(normalPayload.error.details).toBeNull();
    expect(verbose.exitCode).toBe(2);
    expect(verbosePayload.error.details).toContain('Profile source: flag');
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

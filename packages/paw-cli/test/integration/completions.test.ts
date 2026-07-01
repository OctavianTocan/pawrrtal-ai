import { describe, expect, it } from 'vitest';
import { runCli } from './harness';

describe('completions command', (): void => {
  it('generates bash completions for the supported commands', async (): Promise<void> => {
    const result = await runCli({ args: ['completions', 'bash'] });

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain('_paw_doctor');
    expect(result.stdout).toContain('doctor context completions');
  });

  it('generates zsh completions for the supported commands', async (): Promise<void> => {
    const result = await runCli({ args: ['completions', 'zsh'] });

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain('#compdef paw');
    expect(result.stdout).toContain('doctor');
  });
});

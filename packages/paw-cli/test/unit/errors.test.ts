import { describe, expect, it } from 'vitest';
import {
  AuthError,
  ConfigError,
  ExternalError,
  errorToExitCode,
  renderError,
  toCliError,
  UnexpectedError,
  UsageError,
  VerificationError,
} from '../../src/Helpers/Errors';
import { ExitCode } from '../../src/Helpers/ExitCode';

describe('CLI errors', (): void => {
  it('maps tagged errors to public exit codes', (): void => {
    expect(errorToExitCode(new UsageError({ message: 'bad input' }))).toBe(ExitCode.usage);
    expect(errorToExitCode(new ConfigError({ message: 'bad config' }))).toBe(ExitCode.local);
    expect(errorToExitCode(new AuthError({ message: 'denied' }))).toBe(ExitCode.auth);
    expect(errorToExitCode(new ExternalError({ message: 'offline' }))).toBe(ExitCode.external);
    expect(errorToExitCode(new VerificationError({ message: 'failed check' }))).toBe(ExitCode.verification);
    expect(errorToExitCode(new UnexpectedError({ message: 'boom' }))).toBe(ExitCode.local);
  });

  it('normalizes unknown errors for stderr rendering', (): void => {
    const normalized = toCliError(new Error('surprise'));

    expect(normalized._tag).toBe('UnexpectedError');
    expect(renderError(normalized)).toContain('Error: surprise');
  });

  it('renders verbose JSON error details only when requested', (): void => {
    const error = new ExternalError({ message: 'backend unavailable', details: 'socket closed' });

    expect(renderError(error, { isJson: true })).toContain('"details": null');
    expect(renderError(error, { isJson: true, isVerbose: true })).toContain('socket closed');
  });
});

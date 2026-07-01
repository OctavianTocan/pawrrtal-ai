import { Effect } from 'effect';
import { describe, expect, it } from 'vitest';
import {
  AuthError,
  ConfigError,
  ExternalError,
  errorToExitCode,
  renderError,
  renderErrorEffect,
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

  it('normalizes thrown errors for stderr rendering', (): void => {
    const normalized = toCliError(new Error('surprise'));

    expect(normalized._tag).toBe('UnexpectedError');
    expect(renderError(normalized)).toContain('Error: surprise');
  });

  it('renders verbose JSON error details only when requested', (): void => {
    const error = new ExternalError({ message: 'backend unavailable', details: 'socket closed' });

    expect(renderError(error, { isJson: true, isVerbose: false })).toContain('"details": null');
    expect(renderError(error, { isJson: true, isVerbose: true })).toContain('socket closed');
  });

  it('encodes structured JSON error payloads through the public schema', (): void => {
    const error = new UsageError({ message: 'bad input', hint: 'try again' });
    const rendered = Effect.runSync(renderErrorEffect(error, { isJson: true, isVerbose: false }));

    expect(JSON.parse(rendered)).toEqual({
      error: {
        kind: 'usage',
        message: 'bad input',
        hint: 'try again',
        details: null,
      },
    });
  });
});

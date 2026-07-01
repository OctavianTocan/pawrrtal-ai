import { Effect, FileSystem, Layer, Path } from 'effect';
import { CliProcess } from '../../Helpers/Config';
import { CLI_VERSION } from '../../Helpers/Version';
import { ActiveCliContext } from '../../Infrastructure/ActiveContext';
import type { HealthStatus } from './Domain';
import { DoctorReport, DoctorService, HealthCheck } from './Domain';

/** Provides local health checks from the active context and Bun filesystem. */
export const DoctorServiceLive: Layer.Layer<
  DoctorService,
  never,
  ActiveCliContext | CliProcess | FileSystem.FileSystem | Path.Path
> = Layer.effect(
  DoctorService,
  Effect.gen(function* () {
    const context = yield* ActiveCliContext;
    const fs = yield* FileSystem.FileSystem;
    const path = yield* Path.Path;
    const processInfo = yield* CliProcess;

    const run = Effect.fn('DoctorService.run')(function* () {
      const checks = yield* Effect.all(
        [
          checkPass('cli-package-version', CLI_VERSION),
          checkPath(fs, 'config-root', context.configRoot),
          checkPath(fs, 'cache-root', context.cacheRoot),
          checkPass('active-profile', context.profile),
          checkBackendTarget(context.backendTarget),
          checkGeneratedSkill({ fs, path, cwd: processInfo.cwd, name: 'generated-skill:paw', skillName: 'paw' }),
          checkGeneratedSkill({
            fs,
            path,
            cwd: processInfo.cwd,
            name: 'generated-skill:domain-cli',
            skillName: 'domain-cli',
          }),
        ],
        { concurrency: 'unbounded' }
      );

      return new DoctorReport({
        status: overallStatus(checks),
        checks,
      });
    });

    return { run } as const;
  })
);

/** Returns a passing health check. */
function checkPass(name: string, detail: string): Effect.Effect<HealthCheck> {
  return Effect.succeed(new HealthCheck({ name, status: 'pass', detail }));
}

/** Checks whether a filesystem path currently exists. */
function checkPath(fs: FileSystem.FileSystem, name: string, path: string): Effect.Effect<HealthCheck> {
  return fs.exists(path).pipe(
    Effect.map((exists) => ({
      name,
      status: exists ? ('pass' as const) : ('warn' as const),
      detail: exists ? path : `${path} does not exist yet`,
    })),
    Effect.orElseSucceed(() => ({ name, status: 'warn' as const, detail: `${path} could not be inspected` })),
    Effect.map((check) => new HealthCheck(check))
  );
}

/** Checks whether the backend target is configured. */
function checkBackendTarget(backendTarget: string | null): Effect.Effect<HealthCheck> {
  return Effect.succeed(
    new HealthCheck({
      name: 'backend-target',
      status: backendTarget ? 'pass' : 'warn',
      detail: backendTarget ?? 'No backend target configured.',
    })
  );
}

/** Checks whether a generated skill file is present. */
function checkGeneratedSkill(input: {
  readonly fs: FileSystem.FileSystem;
  readonly path: Path.Path;
  readonly cwd: string;
  readonly name: string;
  readonly skillName: string;
}): Effect.Effect<HealthCheck> {
  const filePath = input.path.join(input.cwd, '.agent', 'skills', input.skillName, 'SKILL.md');
  return input.fs.exists(filePath).pipe(
    Effect.map((exists) => ({
      name: input.name,
      status: exists ? ('pass' as const) : ('warn' as const),
      detail: exists ? filePath : `${input.skillName} skill has not been generated`,
    })),
    Effect.orElseSucceed(() => ({
      name: input.name,
      status: 'warn' as const,
      detail: `${input.skillName} skill could not be inspected`,
    })),
    Effect.map((check) => new HealthCheck(check))
  );
}

/** Computes the aggregate doctor status. */
function overallStatus(checks: ReadonlyArray<HealthCheck>): HealthStatus {
  if (checks.some((check) => check.status === 'fail')) {
    return 'fail';
  }
  if (checks.some((check) => check.status === 'warn')) {
    return 'warn';
  }
  return 'pass';
}

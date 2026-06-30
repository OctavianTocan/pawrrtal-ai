import { Context, Effect, FileSystem, Layer, Path } from 'effect';
import { CliProcess } from '../../Helpers/Config';
import { ActiveCliContext } from '../Context/Domain';
import type { DoctorReport, HealthCheck, HealthStatus } from './Domain';

/** Runs local CLI health checks. */
export class DoctorService extends Context.Service<
  DoctorService,
  {
    readonly run: () => Effect.Effect<DoctorReport>;
  }
>()('@pawrrtal/cli/Doctor/Service') {}

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
          checkPass('cli-package-version', '0.1.0'),
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

      return {
        status: overallStatus(checks),
        checks,
      };
    });

    return { run } as const;
  })
);

/** Returns a passing health check. */
function checkPass(name: string, detail: string): Effect.Effect<HealthCheck> {
  return Effect.succeed({ name, status: 'pass', detail });
}

/** Checks whether a filesystem path currently exists. */
function checkPath(fs: FileSystem.FileSystem, name: string, path: string): Effect.Effect<HealthCheck> {
  return fs.exists(path).pipe(
    Effect.map((exists) => ({
      name,
      status: exists ? ('pass' as const) : ('warn' as const),
      detail: exists ? path : `${path} does not exist yet`,
    })),
    Effect.orElseSucceed(() => ({ name, status: 'warn' as const, detail: `${path} could not be inspected` }))
  );
}

/** Checks whether the backend target is configured. */
function checkBackendTarget(backendTarget: string | null): Effect.Effect<HealthCheck> {
  return Effect.succeed({
    name: 'backend-target',
    status: backendTarget ? 'pass' : 'warn',
    detail: backendTarget ?? 'No backend target configured.',
  });
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
    }))
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

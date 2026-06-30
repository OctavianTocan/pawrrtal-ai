import type { FileSystem, Path } from 'effect';
import { Console, Effect } from 'effect';
import { Command } from 'effect/unstable/cli';
import type { CommandMetadata, CommandModule } from '../../Helpers/CommandMetadata';
import { AUTOMATION_FLAG_METADATA, applyCommandMetadata } from '../../Helpers/CommandMetadata';
import type { CliProcess } from '../../Helpers/Config';
import type { UsageError } from '../../Helpers/Errors';
import { ExitCode } from '../../Helpers/ExitCode';
import type { AutomationOptions } from '../../Helpers/Options';
import { automationFlags } from '../../Helpers/Options';
import { formatOutput, resolveOutputMode } from '../../Helpers/Output';
import type { ActiveCliContext } from '../../Infrastructure/ActiveContext';
import { DoctorServiceLive } from './Checks';
import type { DoctorReport } from './Domain';
import { DoctorService } from './Domain';

const DOCTOR_METADATA = {
  name: 'doctor',
  summary: 'Check local Paw CLI readiness',
  description:
    'Check local Paw CLI readiness without contacting the backend by default. Warnings mean setup can continue but something optional is missing.',
  owner: '@pawrrtal/cli/Modules/Doctor',
  flags: AUTOMATION_FLAG_METADATA,
  examples: [
    { command: 'paw doctor', description: 'Run local health checks' },
    { command: 'paw doctor --json', description: 'Run local health checks for automation' },
  ],
  environment: [
    { name: 'PAW_HOME', purpose: 'Overrides config and cache roots used by local checks' },
    { name: 'PAW_PROFILE', purpose: 'Selects the profile checked when --profile is absent' },
    { name: 'PAW_BACKEND_URL', purpose: 'Provides the backend target checked for resolution only' },
  ],
  notes: ['This first slice is local-only and does not contact the backend.', 'Warnings do not make the command fail.'],
  outputModes: ['human', 'json', 'plain'],
  exitCodes: [ExitCode.success, ExitCode.usage, ExitCode.local],
} satisfies CommandMetadata;

/** Command module for local CLI health checks. */
export const DoctorCommand = {
  command: applyCommandMetadata(
    Command.make('doctor', automationFlags, handleDoctor).pipe(Command.provide(DoctorServiceLive)),
    DOCTOR_METADATA
  ),
  metadata: DOCTOR_METADATA,
} satisfies CommandModule<
  'doctor',
  AutomationOptions,
  unknown,
  UsageError,
  ActiveCliContext | CliProcess | FileSystem.FileSystem | Path.Path
>;

/** Runs local health checks and prints the report. */
function handleDoctor(options: AutomationOptions): Effect.Effect<void, UsageError, DoctorService> {
  return Effect.gen(function* () {
    const mode = yield* resolveOutputMode(options);
    const doctor = yield* DoctorService;
    const report = yield* doctor.run();
    yield* Console.log(formatOutput(report, mode, doctorFormatters));
  });
}

const doctorFormatters = {
  human: (report: DoctorReport): string =>
    [
      `Status: ${report.status}`,
      ...report.checks.map((check) => `${check.status.toUpperCase()}: ${check.name} - ${check.detail}`),
    ].join('\n'),
  json: (report: DoctorReport): unknown => report,
  plain: (report: DoctorReport): string =>
    [
      `status\t${report.status}\taggregate`,
      ...report.checks.map((check) => `${check.name}\t${check.status}\t${check.detail}`),
    ].join('\n'),
};

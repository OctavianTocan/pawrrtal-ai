import type { Effect } from 'effect';
import { Context } from 'effect';

export type HealthStatus = 'pass' | 'warn' | 'fail';

export type HealthCheck = {
  readonly name: string;
  readonly status: HealthStatus;
  readonly detail: string;
};

export type DoctorReport = {
  readonly status: HealthStatus;
  readonly checks: ReadonlyArray<HealthCheck>;
};

/** Runs local CLI health checks. */
export class DoctorService extends Context.Service<
  DoctorService,
  {
    readonly run: () => Effect.Effect<DoctorReport>;
  }
>()('@pawrrtal/cli/Doctor/Service') {}

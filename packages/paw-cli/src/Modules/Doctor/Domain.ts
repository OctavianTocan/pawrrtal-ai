import type { Effect } from 'effect';
import { Context, Schema } from 'effect';

export const HealthStatusSchema = Schema.Literals(['pass', 'warn', 'fail']).pipe(
  Schema.annotate({
    identifier: 'HealthStatus',
    title: 'Health Status',
    description: 'Status for a Paw CLI doctor check or aggregate report.',
  })
);

export type HealthStatus = typeof HealthStatusSchema.Type;

export class HealthCheck extends Schema.Class<HealthCheck>('HealthCheck')(
  {
    name: Schema.NonEmptyString,
    status: HealthStatusSchema,
    detail: Schema.NonEmptyString,
  },
  {
    identifier: 'HealthCheck',
    title: 'Health Check',
    description: 'One local readiness check reported by paw doctor.',
  }
) {}

export class DoctorReport extends Schema.Class<DoctorReport>('DoctorReport')(
  {
    status: HealthStatusSchema,
    checks: Schema.Array(HealthCheck),
  },
  {
    identifier: 'DoctorReport',
    title: 'Doctor Report',
    description: 'Aggregate local readiness report emitted by paw doctor.',
  }
) {}

/** Runs local CLI health checks. */
export class DoctorService extends Context.Service<
  DoctorService,
  {
    readonly run: () => Effect.Effect<DoctorReport>;
  }
>()('@pawrrtal/cli/Doctor/Service') {}

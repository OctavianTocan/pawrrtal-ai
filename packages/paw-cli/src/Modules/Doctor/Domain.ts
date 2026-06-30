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

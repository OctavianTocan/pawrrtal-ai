export const ExitCode = {
  success: 0,
  local: 1,
  usage: 2,
  auth: 4,
  external: 5,
  verification: 6,
} as const;

export type ExitCode = (typeof ExitCode)[keyof typeof ExitCode];

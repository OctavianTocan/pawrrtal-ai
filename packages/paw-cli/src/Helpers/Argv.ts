const VERSION_SHORT_FLAG = '-V';
const VERBOSE_SHORT_FLAG = '-v';

/** Normalize Paw's public short aliases before Effect's built-ins parse argv. */
export function normalizeArgv(args: ReadonlyArray<string>): ReadonlyArray<string> {
  return args.map((arg) => {
    if (arg === VERSION_SHORT_FLAG) {
      return '--version';
    }
    if (arg === VERBOSE_SHORT_FLAG) {
      return '--verbose';
    }
    return arg;
  });
}

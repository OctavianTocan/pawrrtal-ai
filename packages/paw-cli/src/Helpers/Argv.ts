const VERSION_SHORT_FLAG = '-V';
const VERBOSE_SHORT_FLAG = '-v';

/**
 * Normalizes Paw's public short aliases before Effect parses argv.
 *
 * @param args - Raw process arguments excluding the executable and script path.
 * @returns Arguments with Paw-specific aliases expanded.
 */
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

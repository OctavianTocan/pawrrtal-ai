export type CliRunOptions = {
  readonly args: ReadonlyArray<string>;
  readonly cwd?: string;
  readonly env?: Readonly<Record<string, string | undefined>>;
};

export type CliRunResult = {
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
};

export const REPO_ROOT = decodeURIComponent(new URL('../../../..', import.meta.url).pathname);

const PACKAGE_ROOT = decodeURIComponent(new URL('../..', import.meta.url).pathname);
const CLI_ENTRYPOINT = decodeURIComponent(new URL('../../src/Main.ts', import.meta.url).pathname);
const LAUNCHER_ENTRYPOINT = pathJoin(REPO_ROOT, 'scripts', 'paw');
const TEMP_ROOT = trimTrailingSlashes(Bun.env.TMPDIR ?? '/tmp');

/**
 * Runs the real Bun CLI entrypoint and captures stdio.
 *
 * @param options - Arguments, cwd, and environment overrides for this invocation.
 * @returns Exit code plus captured stdout and stderr.
 */
export async function runCli(options: CliRunOptions): Promise<CliRunResult> {
  const subprocess = Bun.spawn(['bun', 'run', CLI_ENTRYPOINT, ...options.args], {
    cwd: options.cwd ?? PACKAGE_ROOT,
    env: compactEnv({ ...Bun.env, ...options.env }),
    stdin: 'ignore',
    stdout: 'pipe',
    stderr: 'pipe',
  });

  const [stdout, stderr, exitCode] = await Promise.all([
    subprocess.stdout.text(),
    subprocess.stderr.text(),
    subprocess.exited,
  ]);

  return { exitCode, stdout, stderr };
}

/**
 * Runs the repository launcher script and captures stdio.
 *
 * @param options - Arguments, cwd, and environment overrides for this invocation.
 * @returns Exit code plus captured stdout and stderr.
 */
export async function runLauncher(options: CliRunOptions): Promise<CliRunResult> {
  const subprocess = Bun.spawn([LAUNCHER_ENTRYPOINT, ...options.args], {
    cwd: options.cwd ?? PACKAGE_ROOT,
    env: compactEnv({ ...Bun.env, ...options.env }),
    stdin: 'ignore',
    stdout: 'pipe',
    stderr: 'pipe',
  });

  const [stdout, stderr, exitCode] = await Promise.all([
    subprocess.stdout.text(),
    subprocess.stderr.text(),
    subprocess.exited,
  ]);

  return { exitCode, stdout, stderr };
}

/**
 * Creates a temporary directory for integration tests.
 *
 * @param prefix - Directory name prefix under the OS temp root.
 * @returns Absolute path to the created directory.
 */
export async function makeTempDirectory(prefix: string): Promise<string> {
  const root = pathJoin(TEMP_ROOT, `${prefix}-${crypto.randomUUID()}`);
  await makeDirectory(root);
  return root;
}

/**
 * Writes text after creating the parent directory.
 *
 * @param path - Absolute path to write.
 * @param body - File contents.
 */
export async function writeTextFile(path: string, body: string): Promise<void> {
  await makeDirectory(parentDirectory(path));
  await Bun.write(path, body);
}

/**
 * Reads a text file when present.
 *
 * @param path - Absolute path to read.
 * @returns File text, or empty text when absent.
 */
export async function readTextFileIfExists(path: string): Promise<string> {
  const file = Bun.file(path);
  if (!(await file.exists())) {
    return '';
  }

  return file.text();
}

/**
 * Joins path segments for the POSIX-style paths used by the test workspace.
 *
 * @param segments - Path segments to join.
 * @returns Joined path.
 */
export function pathJoin(...segments: ReadonlyArray<string>): string {
  return segments
    .map((segment, index) => (index === 0 ? trimTrailingSlashes(segment) : trimSlashes(segment)))
    .filter(Boolean)
    .join('/');
}

/** Drops undefined environment overrides before spawning Bun. */
function compactEnv(env: Readonly<Record<string, string | undefined>>): Record<string, string> {
  return Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));
}

/** Creates a directory and its missing parents. */
async function makeDirectory(path: string): Promise<void> {
  const result = Bun.spawnSync(['mkdir', '-p', path], {
    stdout: 'ignore',
    stderr: 'pipe',
  });

  if (!result.success) {
    throw new Error(`Failed to create directory ${path}: ${result.stderr.toString()}`);
  }
}

/** Returns a file path's parent directory. */
function parentDirectory(path: string): string {
  const index = path.lastIndexOf('/');
  if (index <= 0) {
    return '.';
  }

  return path.slice(0, index);
}

/** Removes leading and trailing slashes from a non-root segment. */
function trimSlashes(segment: string): string {
  return segment.replace(/^\/+|\/+$/g, '');
}

/** Removes trailing slashes while preserving the root slash. */
function trimTrailingSlashes(segment: string): string {
  return segment === '/' ? segment : segment.replace(/\/+$/g, '');
}

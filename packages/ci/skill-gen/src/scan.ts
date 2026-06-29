import type { Dirent } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative, resolve } from 'node:path';

const OPEN_TAG = /^\s*(?:\/\/|#)\s*<skill-gen>\s*$/;
const CLOSE_TAG = /^\s*(?:\/\/|#)\s*<\/skill-gen>\s*$/;

const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  '.turbo',
  'dist',
  '.next',
  '.e2e-output',
  'e2e-test',
  'e2e-test-expected',
  'vendor',
  '.context',
  '.worktrees',
]);

const SCANNABLE_EXTENSIONS = new Set([
  '.ts',
  '.tsx',
  '.js',
  '.jsx',
  '.mjs',
  '.cjs',
  '.nix',
  '.py',
  '.rb',
  '.go',
  '.rs',
  '.yaml',
  '.yml',
  '.toml',
  '.sh',
  '.bash',
]);

export interface RawFragment {
  /** Lines between the open/close tags (comment prefixes still intact) */
  lines: string[];
  /** Absolute path to the source file */
  filePath: string;
  /** Path relative to the base folder */
  relativePath: string;
}

/**
 * Collect every skill-gen fragment found beneath a directory tree.
 *
 * @param baseDir - Root directory to search; relative paths are reported from here.
 * @param outputDir - Directory to exclude from the search (the generated output).
 * @param verbose - When true, logs per-file fragment counts to the console.
 * @returns Fragment blocks sorted by relative path for a deterministic merge order.
 */
export async function scan(baseDir: string, outputDir: string, verbose = false): Promise<RawFragment[]> {
  const baseDirResolved = resolve(baseDir);
  const outputDirResolved = resolve(outputDir);
  const filePaths = await collectFiles(baseDirResolved, outputDirResolved);
  const results = await Promise.all(filePaths.map((fp) => processFile(fp, baseDirResolved, verbose)));
  const fragments = results.flat();

  fragments.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  return fragments;
}

/** Whether a file's extension marks it as a candidate to scan for markers. */
function isScannable(fileName: string): boolean {
  const ext = extname(fileName);
  // Files with no extension (e.g. bin/ shebang scripts) are scannable
  return ext === '' || SCANNABLE_EXTENSIONS.has(ext);
}

/** Whether a directory entry should be excluded from traversal. */
function shouldSkipDir(entry: Dirent, fullPath: string, outputDir: string): boolean {
  return SKIP_DIRS.has(entry.name) || fullPath === outputDir;
}

/** Collect every scannable file path under `dir`, excluding skipped and output directories. */
async function collectFiles(dir: string, outputDir: string): Promise<string[]> {
  const files: string[] = [];
  const queue = [dir];

  while (queue.length > 0) {
    const current = queue.shift() ?? dir;
    let entries: Dirent[];
    try {
      entries = await readdir(current, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = join(current, entry.name);

      if (entry.isDirectory() && !shouldSkipDir(entry, fullPath, outputDir)) {
        queue.push(fullPath);
      }

      if (entry.isFile() && isScannable(entry.name)) {
        files.push(fullPath);
      }
    }
  }

  return files;
}

/** Read one file and extract its fragment blocks, or none if it has no markers. */
async function processFile(fullPath: string, baseDir: string, verbose: boolean): Promise<RawFragment[]> {
  let content: string;
  try {
    content = await readFile(fullPath, 'utf-8');
  } catch {
    return [];
  }

  if (!content.includes('<skill-gen>')) {
    return [];
  }

  const fileFragments = extractFragments(content, fullPath, baseDir);
  if (verbose && fileFragments.length > 0) {
    process.stdout.write(`scan: found ${fileFragments.length} fragment(s) in ${relative(baseDir, fullPath)}\n`);
  }
  return fileFragments;
}

/** Begin a new fragment block, rejecting a marker nested inside another. */
function handleOpenTag(currentBlock: string[] | null, filePath: string, lineNum: number): string[] {
  if (currentBlock !== null) {
    throw new Error(`Nested <skill-gen> marker at ${filePath}:${lineNum}. Nested markers are not supported.`);
  }
  return [];
}

/** Close the current fragment block and record it, rejecting an unmatched close marker. */
function handleCloseTag(
  currentBlock: string[] | null,
  filePath: string,
  baseDir: string,
  lineNum: number,
  fragments: RawFragment[]
): void {
  if (currentBlock === null) {
    throw new Error(`Unexpected </skill-gen> without opening tag at ${filePath}:${lineNum}`);
  }
  if (currentBlock.length > 0) {
    fragments.push({
      lines: currentBlock,
      filePath,
      relativePath: relative(baseDir, filePath),
    });
  }
}

/** Extract every fragment block delimited by open/close markers in a file's content. */
function extractFragments(content: string, filePath: string, baseDir: string): RawFragment[] {
  const lines = content.split('\n');
  const fragments: RawFragment[] = [];
  let currentBlock: string[] | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';

    if (OPEN_TAG.test(line)) {
      currentBlock = handleOpenTag(currentBlock, filePath, i + 1);
      continue;
    }

    if (CLOSE_TAG.test(line)) {
      handleCloseTag(currentBlock, filePath, baseDir, i + 1, fragments);
      currentBlock = null;
      continue;
    }

    if (currentBlock !== null) {
      currentBlock.push(line);
    }
  }

  if (currentBlock !== null) {
    throw new Error(`Unclosed <skill-gen> block in ${filePath}`);
  }

  return fragments;
}

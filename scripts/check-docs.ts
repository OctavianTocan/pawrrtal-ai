#!/usr/bin/env bun

/**
 * TSDoc coverage auditor for the Pawrrtal frontend.
 *
 * Scans TypeScript/TSX source files and reports exported declarations that are
 * missing TSDoc/JSDoc block comments (`/** ... *\/`). Outputs per-file findings,
 * aggregate coverage stats, and a ranked list of the worst offenders.
 *
 * Usage:
 *   bun run scripts/check-docs.ts                      # scan all frontend source
 *   bun run scripts/check-docs.ts frontend/lib         # scope to a path prefix
 *   bun run scripts/check-docs.ts --fail-under=80      # exit 1 if coverage < 80%
 *   bun run scripts/check-docs.ts --show-covered       # also list fully-covered files
 *
 * Exit codes:
 *   0 — no violations (or coverage ≥ --fail-under threshold)
 *   1 — missing TSDoc found (or coverage below threshold)
 */

import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import ts from 'typescript';

// ── Config ────────────────────────────────────────────────────────────────────

const REPO_ROOT = path.resolve(import.meta.dir, '..');

/** Source trees to scan (relative to repo root). */
const SCAN_ROOTS = ['frontend'];
const REGEX_METACHARS = new Set(['.', '+', '^', '$', '{', '}', '|', '[', '\\', ']', '(', ')']);

/** Paths / filename patterns to skip entirely. */
const SKIP_PATTERNS: RegExp[] = [
  /node_modules/,
  /[/\\]\.next[/\\]/,
  /[/\\]e2e[/\\]/,
  /[/\\]coverage[/\\]/,
  /[/\\]playwright-report[/\\]/,
  /[/\\]test-results[/\\]/,
  /\.test\.(ts|tsx)$/,
  /\.spec\.(ts|tsx)$/,
  /vitest\.config/,
  /playwright(?:\.stagehand)?\.config/,
  /next\.config/,
  /postcss\.config/,
  /next-env\.d\.ts$/,
];

/** Patterns loaded from `.docignore` at runtime — populated at the start of `main`. */
let docIgnorePatterns: RegExp[] = [];

// ── .docignore support ────────────────────────────────────────────────────────

/**
 * Converts a single gitignore-style glob pattern to a RegExp that matches
 * repo-root-relative paths (forward-slash separated).
 *
 * Supported syntax:
 * - `**\/` at the start or middle → optional path prefix (`(.*\/)?`)
 * - `**` at the end → anything (`.*`)
 * - `*` → any chars except `/` (`[^/]*`)
 * - `?` → any single char except `/` (`[^/]`)
 * - All other regex metacharacters are escaped
 *
 * @param pattern - A single gitignore-style glob (e.g. `frontend/components/**`)
 * @returns RegExp anchored with `^...$` that tests repo-relative forward-slash paths
 */
function globToRegex(pattern: string): RegExp {
  let regexStr = '';
  let i = 0;
  while (i < pattern.length) {
    const ch = pattern.charAt(i);
    if (ch === '*' && pattern[i + 1] === '*') {
      // **/ → optional path prefix; ** at end → anything
      if (pattern[i + 2] === '/') {
        regexStr += '(.*/)?';
        i += 3;
      } else {
        regexStr += '.*';
        i += 2;
      }
    } else if (ch === '*') {
      regexStr += '[^/]*';
      i++;
    } else if (ch === '?') {
      regexStr += '[^/]';
      i++;
    } else if (REGEX_METACHARS.has(ch)) {
      // Escape regex metacharacters that appear in file paths
      regexStr += `\\${ch}`;
      i++;
    } else {
      regexStr += ch;
      i++;
    }
  }
  return new RegExp(`^${regexStr}$`);
}

/**
 * Reads `.docignore` from the repo root and returns compiled RegExp matchers.
 *
 * Each non-empty, non-comment line is treated as a gitignore-style glob.
 * Lines starting with `#` (comments) or `!` (negation — unsupported) are skipped.
 *
 * @returns Array of RegExps for the active ignore patterns, or `[]` if no file found
 */
function loadDocIgnorePatterns(): RegExp[] {
  const ignoreFile = path.join(REPO_ROOT, '.docignore');
  let content: string;
  try {
    content = readFileSync(ignoreFile, 'utf-8');
  } catch {
    return []; // No .docignore present — nothing to exclude
  }
  return content
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#') && !line.startsWith('!'))
    .map(globToRegex);
}

// ── Types ─────────────────────────────────────────────────────────────────────

/** Human-readable category for a declaration. */
type DeclKind = 'function' | 'hook' | 'class' | 'interface' | 'type' | 'enum' | 'constant';

interface MissingDoc {
  name: string;
  kind: DeclKind;
  line: number;
}

interface FileResult {
  /** Repo-root-relative path, e.g. `frontend/lib/utils.ts`. */
  file: string;
  /** Total number of exported declarations audited in this file. */
  total: number;
  /** Declarations that are missing a TSDoc comment. */
  missing: MissingDoc[];
}

// ── File walking ──────────────────────────────────────────────────────────────

function shouldSkip(p: string): boolean {
  if (SKIP_PATTERNS.some((re) => re.test(p))) return true;
  if (docIgnorePatterns.length > 0) {
    // .docignore patterns are repo-relative; normalize separators for cross-platform
    const rel = path.relative(REPO_ROOT, p).replaceAll('\\', '/');
    if (docIgnorePatterns.some((re) => re.test(rel))) return true;
  }
  return false;
}

function walkTs(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (shouldSkip(full)) continue;
    if (entry.isDirectory()) {
      out.push(...walkTs(full));
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

// ── JSDoc detection ───────────────────────────────────────────────────────────

/**
 * Returns true if `node` is immediately preceded by a JSDoc block comment
 * (`/** ... *\/`). JSDoc attaches to the outermost statement node, so callers
 * should pass the statement (e.g. `VariableStatement`) rather than an inner
 * declarator.
 */
function hasLeadingJSDoc(node: ts.Node, sourceFile: ts.SourceFile): boolean {
  const text = sourceFile.getFullText();
  const ranges = ts.getLeadingCommentRanges(text, node.getFullStart());
  if (!ranges || ranges.length === 0) return false;
  // Only the *last* leading comment matters — JSDoc must immediately precede the node.
  const last = ranges.at(-1);
  if (!last) return false;
  if (last.kind !== ts.SyntaxKind.MultiLineCommentTrivia) return false;
  return text.slice(last.pos, last.pos + 3) === '/**';
}

// ── Declaration kind ──────────────────────────────────────────────────────────

/** Maps a name + node pair to a human-readable {@link DeclKind}. */
function inferKind(node: ts.Node, name: string): DeclKind {
  if (ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node)) {
    return name.startsWith('use') ? 'hook' : 'function';
  }
  if (ts.isClassDeclaration(node)) return 'class';
  if (ts.isInterfaceDeclaration(node)) return 'interface';
  if (ts.isTypeAliasDeclaration(node)) return 'type';
  if (ts.isEnumDeclaration(node)) return 'enum';
  return 'constant';
}

// ── Initializer classification ────────────────────────────────────────────────

/**
 * Unwraps `as const` / `as SomeType` type assertions to reach the real
 * value expression.
 */
function unwrapAssertion(expr: ts.Expression): ts.Expression {
  while (ts.isAsExpression(expr)) expr = expr.expression;
  return expr;
}

/**
 * Returns true for primitive literals that don't need a TSDoc comment.
 * Things like `export const FOO = 'bar'` or `export const MAX = 100` are
 * self-documenting from their name and value.
 */
function isTrivialLiteral(expr: ts.Expression): boolean {
  if (ts.isStringLiteral(expr) || ts.isNoSubstitutionTemplateLiteral(expr)) return true;
  if (ts.isNumericLiteral(expr)) return true;
  const k = expr.kind;
  if (
    k === ts.SyntaxKind.TrueKeyword ||
    k === ts.SyntaxKind.FalseKeyword ||
    k === ts.SyntaxKind.NullKeyword ||
    k === ts.SyntaxKind.UndefinedKeyword
  )
    return true;
  // -42 / +42
  if (
    ts.isPrefixUnaryExpression(expr) &&
    (expr.operator === ts.SyntaxKind.MinusToken || expr.operator === ts.SyntaxKind.PlusToken) &&
    ts.isNumericLiteral(expr.operand)
  )
    return true;
  return false;
}

/**
 * Returns true when the variable initializer is interesting enough to require
 * a TSDoc comment (functions, objects, arrays, call results).
 *
 * Skips:
 * - Primitive literals (`'value'`, `42`, `true`, `null`)
 * - Simple identifier references (`export const x = SomeImport`)
 * - Property access chains (`export const x = Foo.Bar`)
 */
function initNeedsDoc(init: ts.Expression | undefined): boolean {
  if (!init) return false;
  const core = unwrapAssertion(init);
  if (isTrivialLiteral(core)) return false;
  if (ts.isIdentifier(core)) return false;
  if (ts.isPropertyAccessExpression(core)) return false;
  return true;
}

// ── Core audit ────────────────────────────────────────────────────────────────

/** Audits a single TypeScript/TSX file and returns its {@link FileResult}. */
function auditFile(filePath: string): FileResult {
  const text = readFileSync(filePath, 'utf-8');
  const scriptKind = filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sourceFile = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, scriptKind);

  const missing: MissingDoc[] = [];
  let total = 0;

  function lineOf(node: ts.Node): number {
    return sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1;
  }

  /** Records a declaration as audited, pushing to `missing` if it lacks JSDoc. */
  function audit(declNode: ts.Node, name: string, stmtNode: ts.Node): void {
    total++;
    if (!hasLeadingJSDoc(stmtNode, sourceFile)) {
      missing.push({ name, kind: inferKind(declNode, name), line: lineOf(declNode) });
    }
  }

  function isExported(node: ts.Node): boolean {
    if (!ts.canHaveModifiers(node)) return false;
    return ts.getModifiers(node)?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword) ?? false;
  }

  function auditNamedDeclaration(node: ts.Node): boolean {
    if (ts.isFunctionDeclaration(node) && node.name) {
      audit(node, node.name.text, node);
      return true;
    }
    if (ts.isClassDeclaration(node) && node.name) {
      audit(node, node.name.text, node);
      return true;
    }
    if (ts.isInterfaceDeclaration(node)) {
      audit(node, node.name.text, node);
      return true;
    }
    if (ts.isTypeAliasDeclaration(node)) {
      audit(node, node.name.text, node);
      return true;
    }
    if (ts.isEnumDeclaration(node)) {
      audit(node, node.name.text, node);
      return true;
    }
    return false;
  }

  function auditVariableStatement(node: ts.VariableStatement): void {
    // export const foo = ..., bar = ...  (multiple declarators are rare but valid)
    for (const decl of node.declarationList.declarations) {
      if (!ts.isIdentifier(decl.name)) continue;
      if (!initNeedsDoc(decl.initializer)) continue;
      // JSDoc attaches to the VariableStatement (the outer `export const …`),
      // not to individual VariableDeclarations inside it.
      audit(decl.initializer ?? decl, decl.name.text, node);
    }
  }

  function visitExported(node: ts.Node): boolean {
    if (!isExported(node)) return false;
    if (auditNamedDeclaration(node)) return true;
    if (ts.isVariableStatement(node)) {
      auditVariableStatement(node);
      return true;
    }
    return false;
  }

  function visit(node: ts.Node): void {
    if (visitExported(node)) return;
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);

  return { file: path.relative(REPO_ROOT, filePath), total, missing };
}

// ── ANSI colours ──────────────────────────────────────────────────────────────

const C = {
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  reset: '\x1b[0m',
} as const;

const KIND_COLOR: Record<DeclKind, string> = {
  hook: C.cyan,
  function: C.yellow,
  class: C.green,
  interface: C.cyan,
  type: C.dim,
  enum: C.yellow,
  constant: C.dim,
};

function coveragePct(covered: number, total: number): number {
  return total === 0 ? 100 : (covered / total) * 100;
}

// ── Main ──────────────────────────────────────────────────────────────────────

interface CliOptions {
  failUnder: number | null;
  scopeArg: string | undefined;
  showCovered: boolean;
}

function parseCliOptions(args: string[]): CliOptions {
  // --fail-under=<number>  exit 1 if overall coverage is below this %
  const failUnderArg = args.find((a) => a.startsWith('--fail-under='));
  const failUnderValue = failUnderArg?.slice('--fail-under='.length);

  return {
    failUnder: failUnderValue ? Number.parseFloat(failUnderValue) : null,
    // Positional arg: path prefix to scope the scan (e.g. "frontend/lib")
    scopeArg: args.find((a) => !a.startsWith('--')),
    // --show-covered  also list files with 100% coverage
    showCovered: args.includes('--show-covered'),
  };
}

function collectFiles(scopeArg: string | undefined): string[] {
  const files: string[] = [];
  for (const root of SCAN_ROOTS) {
    const abs = path.join(REPO_ROOT, root);
    for (const f of walkTs(abs)) {
      if (!scopeArg || path.relative(REPO_ROOT, f).startsWith(scopeArg)) {
        files.push(f);
      }
    }
  }
  return files;
}

function auditFiles(files: string[]): FileResult[] {
  return (
    files
      .map(auditFile)
      .filter((r) => r.total > 0)
      // Sort: most missing first, then alphabetically
      .sort((a, b) => b.missing.length - a.missing.length || a.file.localeCompare(b.file))
  );
}

function totalsFor(results: FileResult[]): { totalExports: number; totalMissing: number } {
  let totalExports = 0;
  let totalMissing = 0;

  for (const r of results) {
    totalExports += r.total;
    totalMissing += r.missing.length;
  }
  return { totalExports, totalMissing };
}

function printFileResults(results: FileResult[], showCovered: boolean): void {
  for (const r of results) {
    const fullyDone = r.missing.length === 0;
    if (fullyDone && !showCovered) continue;

    const covered = r.total - r.missing.length;
    const pct = coveragePct(covered, r.total);
    const pctStr = pct.toFixed(0);
    const pctColor = pct === 100 ? C.green : pct >= 50 ? C.yellow : C.red;

    console.log(
      `\n${C.bold}${C.cyan}${r.file}${C.reset}` +
        `  ${pctColor}${pctStr}%${C.reset}` +
        `  ${C.dim}(${covered}/${r.total})${C.reset}`
    );

    for (const m of r.missing) {
      const kindStr = `${KIND_COLOR[m.kind]}${m.kind}${C.reset}`;
      console.log(
        `  ${C.red}✗${C.reset}  ${C.bold}${m.name}${C.reset}` + `  ${kindStr}` + `  ${C.dim}line ${m.line}${C.reset}`
      );
    }
  }
}

function printSummary(files: string[], results: FileResult[]): { overallPct: number; totalMissing: number } {
  const { totalExports, totalMissing } = totalsFor(results);
  const totalCovered = totalExports - totalMissing;
  const overallPct = coveragePct(totalCovered, totalExports);
  const overallColor = overallPct >= 80 ? C.green : overallPct >= 60 ? C.yellow : C.red;

  const SEP = `${C.dim}${'─'.repeat(60)}${C.reset}`;
  console.log(`\n${SEP}`);
  console.log(`${C.bold}TSDoc Coverage${C.reset}`);
  console.log(SEP);
  console.log(`  Files scanned:    ${files.length}`);
  console.log(`  Files with exports: ${results.length}`);
  console.log(`  Exports audited:  ${totalExports}`);
  console.log(`  ${C.green}✓${C.reset} With TSDoc:    ${C.bold}${totalCovered}${C.reset} of ${totalExports}`);
  console.log(`  ${C.red}✗${C.reset} Missing:       ${C.bold}${totalMissing}${C.reset}`);
  console.log(`  Coverage:         ${overallColor}${C.bold}${overallPct.toFixed(1)}%${C.reset}`);

  const offenders = results.filter((r) => r.missing.length > 0);
  if (offenders.length > 0) {
    console.log(`\n${C.bold}Top offenders:${C.reset}`);
    for (const r of offenders.slice(0, 10)) {
      const n = String(r.missing.length).padStart(3);
      const bar = '▪'.repeat(Math.min(r.missing.length, 30));
      console.log(`  ${C.red}${n}${C.reset} missing  ${r.file}  ${C.dim}${bar}${C.reset}`);
    }
  }

  console.log();
  return { overallPct, totalMissing };
}

function exitForFailures(failUnder: number | null, overallPct: number, totalMissing: number): void {
  if (failUnder !== null && overallPct < failUnder) {
    console.error(
      `${C.red}${C.bold}✗ Coverage ${overallPct.toFixed(1)}% is below the required ` +
        `minimum of ${failUnder}% (--fail-under)${C.reset}`
    );
    process.exit(1);
  }

  if (totalMissing > 0) process.exit(1);
}

function main(): void {
  // Load .docignore exclusions before any file walking
  docIgnorePatterns = loadDocIgnorePatterns();

  const options = parseCliOptions(process.argv.slice(2));
  const files = collectFiles(options.scopeArg);
  const results = auditFiles(files);

  printFileResults(results, options.showCovered);
  const { overallPct, totalMissing } = printSummary(files, results);
  exitForFailures(options.failUnder, overallPct, totalMissing);
}

main();

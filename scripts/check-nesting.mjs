#!/usr/bin/env node
/**
 * Repo-wide nesting-depth lint for TypeScript / TSX sources.
 *
 * Walks the frontend tree, parses each file with the official TypeScript
 * compiler API, and reports every function whose maximum control-flow
 * nesting depth exceeds the configured budget (default: 3 — at most three
 * levels of compound-statement nesting inside a single function body).
 *
 * Sibling to:
 *   - `scripts/check-file-lines.mjs`  (file-length budget, TS/TSX/PY)
 *   - `scripts/check-nesting.py`      (Python nesting, AST-based)
 *
 * Counted compound statements:
 *   - IfStatement
 *   - ForStatement / ForInStatement / ForOfStatement
 *   - WhileStatement / DoStatement
 *   - TryStatement (counted once — its catch/finally don't add depth)
 *   - SwitchStatement
 *   - WithStatement (just in case — depth budget should kill it on sight)
 *
 * NOT counted (different smells, addressed by other lints):
 *   - Ternaries (`a ? b : c`) — Biome covers complex expressions.
 *   - Logical short-circuit (`a && b`) — same.
 *   - Block statements (`{ ... }`) — they're a syntactic grouping, not a
 *     control-flow level.
 *   - Nested function / arrow / class declarations — those are a fresh
 *     scope and we recurse into them with depth reset to 0, so an inline
 *     callback inside a for-loop doesn't blow the budget on its own.
 *
 * Why a custom script rather than a Biome rule: Biome ships
 * `noExcessiveCognitiveComplexity` which conflates several signals
 * (nesting, branch count, recursion) into a single number.  This is
 * intentionally one narrow signal — easy to read, easy to override,
 * easy to remove if a better off-the-shelf option lands.
 *
 * Usage:
 *   node scripts/check-nesting.mjs              # default depth 3
 *   MAX_DEPTH=2 node scripts/check-nesting.mjs  # tighter
 *
 * Exit codes:
 *   0 — every scanned function is within budget
 *   1 — at least one function exceeds the budget; offenders are printed
 */

import { promises as fs } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const require_ = createRequire(import.meta.url);

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');

/** Hard ceiling — functions beyond this fail the check. */
const MAX_DEPTH = Number.parseInt(process.env.MAX_DEPTH ?? '3', 10);

/** Roots we scan. Add new top-level source trees here. */
const SCAN_ROOTS = ['frontend', 'backend-ts'];

/** Directory names we never descend into. */
const SKIP_DIRECTORIES = new Set([
	'node_modules',
	'.next',
	'dist',
	'build',
	'.venv',
	'__pycache__',
	'.beans',
	'.claude',
	'.cursor',
	'.agents',
	'.codex',
	'.opencode',
	'.crush',
	'.zed',
	'.vscode',
	'.sentrux',
	'.private',
	'alembic',
	'tests',
	'__tests__',
]);

/** File extensions we care about. */
const TARGET_EXTENSIONS = new Set(['.ts', '.tsx']);

/** Suffixes that are exempt (test/spec files can nest more freely). */
const EXEMPT_SUFFIXES = ['.test.ts', '.test.tsx', '.spec.ts', '.spec.tsx', '.d.ts'];

/**
 * Repo-relative `path::function` keys exempt from the budget.
 *
 * Pre-existing tech debt — each entry should be tracked in a follow-up
 * bean and removed once the function is flattened.  Mirror of the
 * `EXEMPT_FUNCTIONS` discipline in `scripts/check-nesting.py`.
 *
 * DO NOT add new entries here as a workaround.  New code must come in
 * under the budget; if you genuinely cannot, raise it in review.
 *
 * Seeded empty — populated on first CI run if any pre-existing
 * frontend code breaches the budget.
 */
const EXEMPT_FUNCTIONS = new Set([]);

/**
 * Repo-relative path fragments exempt from scanning entirely.
 *
 * Mirrors the same vendored / generated carve-outs from
 * `scripts/check-file-lines.mjs` — files we don't own can't be held
 * to our local style budget.
 */
const EXEMPT_PATH_FRAGMENTS = [
	'frontend/components/ui/', // shadcn-generated primitives
	'frontend/lib/react-dropdown/', // vendored sibling package
	'frontend/lib/react-overlay/', // vendored sibling package
	'frontend/lib/react-chat-composer/', // vendored sibling package
	'routeTree.gen.ts', // TanStack Router generated tree
];

const ts = require_('typescript');

/**
 * Compound-statement node kinds.  Hitting one of these inside a
 * function body increments the nesting depth by 1.
 */
const NESTING_KINDS = new Set([
	ts.SyntaxKind.IfStatement,
	ts.SyntaxKind.ForStatement,
	ts.SyntaxKind.ForInStatement,
	ts.SyntaxKind.ForOfStatement,
	ts.SyntaxKind.WhileStatement,
	ts.SyntaxKind.DoStatement,
	ts.SyntaxKind.TryStatement,
	ts.SyntaxKind.SwitchStatement,
	ts.SyntaxKind.WithStatement,
]);

/**
 * Function-like node kinds.  Entering one resets the depth to 0 so
 * an inline callback inside a deep for-loop doesn't inherit the
 * outer nesting (we'd flag the outer for-loop on its own merits).
 */
const FUNCTION_KINDS = new Set([
	ts.SyntaxKind.FunctionDeclaration,
	ts.SyntaxKind.FunctionExpression,
	ts.SyntaxKind.ArrowFunction,
	ts.SyntaxKind.MethodDeclaration,
	ts.SyntaxKind.GetAccessor,
	ts.SyntaxKind.SetAccessor,
	ts.SyntaxKind.Constructor,
]);

/** Best-effort name for a function-like node. */
function functionName(node, parent) {
	if (node.name?.escapedText) return String(node.name.escapedText);
	// Arrow / function expression assigned to a variable: `const foo = () => {}`.
	if (parent && parent.kind === ts.SyntaxKind.VariableDeclaration && parent.name) {
		return String(parent.name.escapedText ?? parent.name.getText?.() ?? '<anonymous>');
	}
	// Property assignment: `{ foo: () => {} }`.
	if (parent && parent.kind === ts.SyntaxKind.PropertyAssignment && parent.name) {
		return String(parent.name.escapedText ?? parent.name.getText?.() ?? '<anonymous>');
	}
	if (node.kind === ts.SyntaxKind.Constructor) return 'constructor';
	return '<anonymous>';
}

/**
 * Recursively walk `node`, tracking the deepest nesting reached
 * inside the current function body.  When we cross into a new
 * function-like node we reset the depth and record that function's
 * deepest reach independently.
 */
function analyse(sourceFile) {
	const offenders = [];

	function walk(node, parent, currentDepth, currentFunction) {
		if (FUNCTION_KINDS.has(node.kind)) {
			const name = functionName(node, parent);
			const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart());
			const fnState = { name, line: line + 1, deepest: 0 };
			ts.forEachChild(node, (child) => walk(child, node, 0, fnState));
			if (fnState.deepest > MAX_DEPTH) {
				offenders.push(fnState);
			}
			return;
		}

		let nextDepth = currentDepth;
		if (NESTING_KINDS.has(node.kind)) {
			nextDepth = currentDepth + 1;
			if (currentFunction && nextDepth > currentFunction.deepest) {
				currentFunction.deepest = nextDepth;
			}
		}

		ts.forEachChild(node, (child) => walk(child, node, nextDepth, currentFunction));
	}

	ts.forEachChild(sourceFile, (child) => walk(child, sourceFile, 0, null));
	return offenders;
}

/** Recursively yield every TS/TSX source file under `dir` we should check. */
async function* walkDir(dir) {
	let entries;
	try {
		entries = await fs.readdir(dir, { withFileTypes: true });
	} catch {
		return;
	}
	for (const entry of entries) {
		if (entry.isDirectory()) {
			if (SKIP_DIRECTORIES.has(entry.name)) continue;
			yield* walkDir(path.join(dir, entry.name));
			continue;
		}
		if (!entry.isFile()) continue;
		const ext = path.extname(entry.name);
		if (!TARGET_EXTENSIONS.has(ext)) continue;
		if (EXEMPT_SUFFIXES.some((suffix) => entry.name.endsWith(suffix))) continue;
		yield path.join(dir, entry.name);
	}
}

async function checkFile(filePath, repoRelative) {
	const source = await fs.readFile(filePath, 'utf8');
	const scriptKind = filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
	const sourceFile = ts.createSourceFile(
		filePath,
		source,
		ts.ScriptTarget.Latest,
		/* setParentNodes */ true,
		scriptKind
	);
	const offenders = analyse(sourceFile);
	return offenders
		.filter((o) => !EXEMPT_FUNCTIONS.has(`${repoRelative}::${o.name}`))
		.map((o) => ({ path: repoRelative, ...o }));
}

async function main() {
	const all = [];
	for (const root of SCAN_ROOTS) {
		const absoluteRoot = path.join(REPO_ROOT, root);
		try {
			await fs.access(absoluteRoot);
		} catch {
			continue;
		}
		for await (const filePath of walkDir(absoluteRoot)) {
			const relative = path.relative(REPO_ROOT, filePath);
			if (EXEMPT_PATH_FRAGMENTS.some((fragment) => relative.includes(fragment))) {
				continue;
			}
			const offenders = await checkFile(filePath, relative);
			all.push(...offenders);
		}
	}

	if (all.length === 0) {
		console.log(`check-nesting: OK (no functions exceed depth ${MAX_DEPTH})`);
		return;
	}

	all.sort((a, b) => b.deepest - a.deepest || a.path.localeCompare(b.path) || a.line - b.line);
	console.error(`check-nesting: ${all.length} function(s) exceed depth ${MAX_DEPTH}:\n`);
	for (const o of all) {
		console.error(`  depth=${o.deepest}  ${o.path}:${o.line}  in ${o.name}()`);
	}
	console.error(
		'\nFlatten with guard clauses or extract helpers to bring each function under the budget.'
	);
	process.exitCode = 1;
}

await main();

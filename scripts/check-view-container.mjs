#!/usr/bin/env node
/**
 * Repo-wide View/Container split audit for React TSX sources.
 *
 * Pairs with the project's [view-container-split rule]
 * (`.claude/rules/react/view-container-split.md`): containers own hooks and
 * state, views are pure presentation. This script walks the frontend TSX tree
 * with the TypeScript compiler API and flags two distinct violations:
 *
 *   1. IMPURE_VIEW — a file whose basename ends with `View.tsx` (i.e. it's
 *      declared as a pure presentation surface) but which calls a React hook
 *      outside the pure-derivation allowlist {`useId`, `useMemo`,
 *      `useCallback`, `useMediaQuery`}. Anything else (state, effects, refs,
 *      reducers, data-fetching hooks) belongs in the paired container, not the
 *      view.
 *
 *   2. MONOLITH — a non-view component file exceeding the line budget
 *      (`MONOLITH_LOC_THRESHOLD`, default 80) AND calling at least
 *      `MONOLITH_MIN_HOOKS` (default 3) React hooks AND rendering JSX. These
 *      are good candidates for a View/Container split. Score is
 *      `hookCount * ceil(lineCount / 100)` so big-and-hook-heavy files surface
 *      first.
 *
 * Sibling to:
 *   - `scripts/check-file-lines.mjs`  (file-length budget, TS/TSX/PY)
 *   - `scripts/check-nesting.mjs`     (TS/TSX nesting depth, AST-based)
 *
 * Modes:
 *   - Advisory (default) — exits 0, prints offenders to stderr. Use this to
 *     introduce the rule without breaking CI.
 *   - Strict (`STRICT_VC=1`) — exits 1 on any non-exempt offender.
 *
 * Usage:
 *   node scripts/check-view-container.mjs              # advisory
 *   STRICT_VC=1 node scripts/check-view-container.mjs  # blocking
 *   MONOLITH_LOC_THRESHOLD=120 node scripts/check-view-container.mjs
 *   MONOLITH_MIN_HOOKS=4       node scripts/check-view-container.mjs
 *
 * Exit codes:
 *   0 — no offenders, or offenders found but STRICT_VC is unset
 *   1 — STRICT_VC=1 and at least one non-exempt offender
 */

import { promises as fs } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const require_ = createRequire(import.meta.url);

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');

/** Strict mode fails CI on any non-exempt offender; unset is advisory. */
const IS_STRICT = process.env.STRICT_VC === '1';

/** Minimum lines-of-code in a non-view component to be considered a MONOLITH candidate. */
const MONOLITH_LOC_THRESHOLD = Number.parseInt(process.env.MONOLITH_LOC_THRESHOLD ?? '80', 10);

/** Minimum number of hook calls in a non-view component to be considered a MONOLITH candidate. */
const MONOLITH_MIN_HOOKS = Number.parseInt(process.env.MONOLITH_MIN_HOOKS ?? '3', 10);

/** Roots we scan. Component files only live under these trees. */
const SCAN_ROOTS = ['frontend/features', 'frontend/components'];

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
	'tests',
	'__tests__',
]);

/** Only `.tsx` files declare components — `.ts` is plumbing. */
const TARGET_EXTENSIONS = new Set(['.tsx']);

/** Tests, stories, type defs, and Next.js entry points are exempt. */
const EXEMPT_SUFFIXES = ['.test.tsx', '.spec.tsx', '.stories.tsx', '.d.ts'];

/** Bare filenames (no leading directory) that are always exempt. */
const EXEMPT_FILENAMES = new Set([
	'page.tsx',
	'layout.tsx',
	'loading.tsx',
	'error.tsx',
	'not-found.tsx',
]);

/**
 * Repo-relative path fragments exempt from scanning entirely.
 *
 * Mirrors the carve-outs from `scripts/check-file-lines.mjs` /
 * `scripts/check-nesting.mjs` — files we don't own can't be held to our local
 * split rules.
 */
const EXEMPT_PATH_FRAGMENTS = [
	'frontend/components/ui/', // shadcn-generated primitives
	'frontend/components/ai-elements/', // vendored upstream AI Elements
	'frontend/lib/react-dropdown/', // vendored sibling package
	'frontend/lib/react-overlay/', // vendored sibling package
	'frontend/lib/react-chat-composer/', // vendored sibling package
	'routeTree.gen.ts', // TanStack Router generated
];

/**
 * Repo-relative paths exempt from the audit because they're pre-existing tech
 * debt at the time this script was introduced.
 *
 * Each entry must be paired with a TODO comment + a follow-up bean. Do not
 * grow this set as a workaround for new code — new components must come in
 * under the rule. Mirror of the `EXEMPT_FUNCTIONS` discipline in
 * `scripts/check-nesting.mjs`.
 *
 * Seeded by the first run of this script against the codebase as of the
 * `feat/extract-react-chat-composer` branch — 3 IMPURE_VIEW offenders and 24
 * MONOLITH offenders captured here. The three chat-composer files this PR
 * splits are intentionally NOT exempted; they should disappear from the
 * offender list after the split lands.
 *
 * TODO(pawrrtal-f1vm follow-up): file one bean per entry to track the View /
 * Container split. Remove each entry from the set as its split lands.
 */
const EXEMPT_FILES = new Set([
	// IMPURE_VIEW — views that still reach for hooks beyond the allowlist.
	'frontend/features/chat/ChatView.tsx',
	'frontend/features/nav-chats/components/NavChatsView.tsx',
	'frontend/features/nav-chats/components/ConversationSidebarItemView.tsx',
	// MONOLITH — non-view components big enough to warrant a split. Sorted by
	// score descending to match the audit output the day this list was seeded.
	'frontend/features/settings/sections/AppearanceSection.tsx',
	'frontend/features/chat/ChatContainer.tsx',
	'frontend/features/knowledge/components/DocumentViewer.tsx',
	'frontend/features/tasks/TasksContainer.tsx',
	'frontend/features/nav-chats/context/sidebar-focus.tsx',
	'frontend/features/settings/sections/AppearanceRows.tsx',
	'frontend/features/nav-chats/NavChats.tsx',
	'frontend/features/onboarding/v2/OnboardingFlow.tsx',
	'frontend/features/projects/components/ProjectsList.tsx',
	'frontend/features/settings/primitives.tsx',
	'frontend/features/onboarding/OnboardingModal.tsx',
	'frontend/components/signup-form.tsx',
	'frontend/components/nav-user.tsx',
	'frontend/features/channels/TelegramConnectDialog.tsx',
	'frontend/features/auth/LoginForm.tsx',
	'frontend/features/chat/components/AssistantMessage.tsx',
	'frontend/features/knowledge/components/MyFilesPanel.tsx',
	'frontend/features/settings/sections/PersonalizationSection.tsx',
	'frontend/features/knowledge/KnowledgeContainer.tsx',
	'frontend/features/projects/components/CreateProjectModal.tsx',
	'frontend/features/settings/SettingsLayout.tsx',
	'frontend/features/nav-chats/context/chat-activity-context.tsx',
]);

/**
 * Hook names that are safe to call inside a `*View.tsx` file. They cover pure
 * derivations (`useMemo`, `useCallback`), DOM id stability (`useId`), and
 * viewport queries (`useMediaQuery`). Anything else — including `useState`,
 * `useEffect`, `useRef`, `useReducer`, custom hooks — belongs in the paired
 * container.
 */
const PURE_VIEW_HOOK_ALLOWLIST = new Set(['useId', 'useMemo', 'useCallback', 'useMediaQuery']);

const ts = require_('typescript');

/** Names that fit the React hook convention: `use<Uppercase>`. */
function isHookName(name) {
	return typeof name === 'string' && /^use[A-Z]/.test(name);
}

/**
 * Walk the source file once, collecting:
 *   - every hook call (callee name + line) — used by MONOLITH scoring and the
 *     IMPURE_VIEW callee check
 *   - whether the file renders JSX at all — gates MONOLITH (a pure utility
 *     module with hooks isn't a component)
 */
function analyseFile(sourceFile) {
	const hookCalls = [];
	let hasJsx = false;

	function visit(node) {
		// JSX detection covers both `<div />` and `<Frag>`.
		if (
			node.kind === ts.SyntaxKind.JsxElement ||
			node.kind === ts.SyntaxKind.JsxSelfClosingElement ||
			node.kind === ts.SyntaxKind.JsxFragment
		) {
			hasJsx = true;
		}

		if (node.kind === ts.SyntaxKind.CallExpression) {
			const callee = node.expression;
			let name;
			if (callee.kind === ts.SyntaxKind.Identifier) {
				name = String(callee.escapedText ?? callee.text ?? '');
			} else if (
				callee.kind === ts.SyntaxKind.PropertyAccessExpression &&
				callee.name &&
				callee.name.kind === ts.SyntaxKind.Identifier
			) {
				// Matches `React.useState()`, `something.useFoo()`.
				name = String(callee.name.escapedText ?? callee.name.text ?? '');
			}
			if (name && isHookName(name)) {
				const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart());
				hookCalls.push({ name, line: line + 1 });
			}
		}

		ts.forEachChild(node, visit);
	}

	ts.forEachChild(sourceFile, visit);
	return { hookCalls, hasJsx };
}

function countLines(source) {
	if (source.length === 0) return 0;
	// `split('\n').length` is one off when the file lacks a trailing newline,
	// but the difference of 1 is irrelevant against the LOC threshold.
	return source.split('\n').length;
}

/**
 * Returns true when `filePath` has a paired `{name}View.tsx` sibling in the
 * same directory. A file with a paired View has already been split, so it
 * should be treated as a container — not a MONOLITH candidate, no matter
 * how many hooks it calls. (Containers are *expected* to call hooks.)
 */
async function hasPairedView(filePath) {
	const dir = path.dirname(filePath);
	const baseName = path.basename(filePath, '.tsx');
	// Views don't pair with themselves; only checked for non-View files.
	if (baseName.endsWith('View')) return false;
	const candidate = path.join(dir, `${baseName}View.tsx`);
	try {
		await fs.access(candidate);
		return true;
	} catch {
		return false;
	}
}

/** Returns the list of offenders found in `filePath`. */
async function checkFile(filePath, repoRelative) {
	const source = await fs.readFile(filePath, 'utf8');
	const sourceFile = ts.createSourceFile(
		filePath,
		source,
		ts.ScriptTarget.Latest,
		/* setParentNodes */ true,
		ts.ScriptKind.TSX
	);
	const { hookCalls, hasJsx } = analyseFile(sourceFile);
	const lineCount = countLines(source);
	const baseName = path.basename(filePath);
	const isView = baseName.endsWith('View.tsx');

	const offenders = [];

	if (isView) {
		// IMPURE_VIEW: any hook outside the pure-derivation allowlist.
		const impureHooks = hookCalls.filter((hook) => !PURE_VIEW_HOOK_ALLOWLIST.has(hook.name));
		if (impureHooks.length > 0) {
			offenders.push({
				severity: 'IMPURE_VIEW',
				path: repoRelative,
				score: impureHooks.length,
				summary: `${impureHooks.length} disallowed hook call(s): ${impureHooks
					.slice(0, 4)
					.map((hook) => `${hook.name}() @ L${hook.line}`)
					.join(', ')}${impureHooks.length > 4 ? ', …' : ''}`,
				detail: { hookCount: hookCalls.length, lineCount, impureHooks },
			});
		}
		return offenders;
	}

	// MONOLITH path: only relevant for files that actually render JSX.
	if (!hasJsx) return offenders;
	if (lineCount < MONOLITH_LOC_THRESHOLD) return offenders;
	if (hookCalls.length < MONOLITH_MIN_HOOKS) return offenders;
	// A file with a paired `*View.tsx` sibling has already been split — it's a
	// container, and containers are expected to call hooks. Don't flag.
	if (await hasPairedView(filePath)) return offenders;

	const score = hookCalls.length * Math.ceil(lineCount / 100);
	offenders.push({
		severity: 'MONOLITH',
		path: repoRelative,
		score,
		summary: `score=${score} hooks=${hookCalls.length} loc=${lineCount} — candidate for View/Container split`,
		detail: { hookCount: hookCalls.length, lineCount },
	});
	return offenders;
}

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
		if (EXEMPT_FILENAMES.has(entry.name)) continue;
		yield path.join(dir, entry.name);
	}
}

async function main() {
	const offenders = [];
	for (const root of SCAN_ROOTS) {
		const absoluteRoot = path.join(REPO_ROOT, root);
		try {
			await fs.access(absoluteRoot);
		} catch {
			continue;
		}
		for await (const filePath of walkDir(absoluteRoot)) {
			const relative = path.relative(REPO_ROOT, filePath);
			if (EXEMPT_PATH_FRAGMENTS.some((fragment) => relative.includes(fragment))) continue;
			if (EXEMPT_FILES.has(relative)) continue;
			const fileOffenders = await checkFile(filePath, relative);
			offenders.push(...fileOffenders);
		}
	}

	if (offenders.length === 0) {
		console.log('check-view-container: OK (no IMPURE_VIEW or MONOLITH offenders)');
		return;
	}

	// IMPURE_VIEW is more severe than MONOLITH (the rule was explicitly broken
	// rather than a soft signal that a file is growing). Sort by severity, then
	// score descending, then path for stability.
	const severityRank = { IMPURE_VIEW: 0, MONOLITH: 1 };
	offenders.sort(
		(left, right) =>
			severityRank[left.severity] - severityRank[right.severity] ||
			right.score - left.score ||
			left.path.localeCompare(right.path)
	);

	const impureCount = offenders.filter((o) => o.severity === 'IMPURE_VIEW').length;
	const monolithCount = offenders.filter((o) => o.severity === 'MONOLITH').length;
	const mode = IS_STRICT ? 'STRICT' : 'advisory';
	console.error(
		`check-view-container [${mode}]: ${impureCount} IMPURE_VIEW, ${monolithCount} MONOLITH offender(s):\n`
	);
	for (const offender of offenders) {
		console.error(
			`  ${offender.severity.padEnd(12)}  ${offender.path}\n      ${offender.summary}`
		);
	}
	console.error(
		'\nIMPURE_VIEW: move the disallowed hooks into the paired container component.\nMONOLITH: split into a `<Name>Container.tsx` (hooks + state) + `<Name>View.tsx` (pure presentation).\nSee `.claude/rules/react/view-container-split.md` for the pattern.'
	);

	if (IS_STRICT) process.exitCode = 1;
}

await main();

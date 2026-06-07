#!/usr/bin/env node
/**
 * Repo-wide file-length lint.
 *
 * Errors when any TypeScript / TSX / Python source file exceeds the
 * `MAX_LINES` budget. Biome 2.x ships `noExcessiveLinesPerFunction` but no
 * equivalent file-level rule; this script is the sibling check we run
 * alongside `biome check` so CI fails on bloat.
 *
 * Usage:
 *   node scripts/check-file-lines.mjs            # checks the default tree
 *   MAX_LINES=400 node scripts/check-file-lines.mjs   # tighter override
 *
 * Exit codes:
 *   0 — every scanned file is within budget
 *   1 — at least one file exceeds the budget; offenders are printed
 */

import { promises as fs } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');

/** Hard ceiling — files beyond this fail the check. */
const MAX_LINES = Number.parseInt(process.env.MAX_LINES ?? '500', 10);

/** Roots we scan. Add new top-level source trees here. */
const SCAN_ROOTS = ['frontend', 'backend', 'backend-ts'];

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
	'vendor', // vendored submodules (e.g. backend/vendor/codex) follow their own line conventions
]);

/** File extensions we care about. */
const TARGET_EXTENSIONS = new Set(['.ts', '.tsx', '.py']);

/** Files matching any of these suffixes are exempt (tests, generated, etc). */
const EXEMPT_SUFFIXES = ['.test.ts', '.test.tsx', '.spec.ts', '.spec.tsx', '.d.ts'];

/**
 * Repo-relative path fragments that are exempt from the file-length budget.
 *
 * `components/ui/` is shadcn-generated and already exempted by Biome (see
 * `biome.json` overrides) — applying our budget there would mean editing
 * upstream-tracked primitives. Other entries are pre-existing tech debt
 * tracked in their own follow-up beans; remove the entry once the file is
 * split rather than letting the exemption become permanent.
 */
const EXEMPT_PATH_FRAGMENTS = [
	'frontend/packages/', // vendored workspace packages (see biome.json overrides)
	'frontend/components/ui/',
	// `frontend/lib/react-dropdown/` is a vendored copy of the
	// `@octavian-tocan/react-dropdown` package that lives in its own git
	// repo (gitignored from this one). Its file-length conventions belong
	// to the package, not the host app — this budget would force splits
	// that don't match upstream's structure.
	'frontend/lib/react-dropdown/',
	'frontend/lib/react-overlay/',
	'frontend/lib/react-chat-composer/',
	// CCT-integration stack (PRs feat/cct-03 onward) extended each of these
	// modules. They were already near the budget on `development`
	// (claude_provider.py was 499 lines pre-CCT), and the per-PR additions
	// are too small individually to justify in-PR splits. Tracked as a
	// follow-up to extract:
	//   - agent_loop/loop.py → agent_loop/permission_gate.py (PR 03 addition)
	//   - providers/claude_provider.py → split sandbox/retry/multimodal helpers (PR 05)
	//   - integrations/telegram/bot.py → split typing-indicator + permission helpers (PR 03 + PR 07)
	// TODO(pawrrtal-cct follow-up): split these and remove the exemption.
	'backend/app/agents/loop.py',
	'backend/app/providers/claude/provider.py',
	'backend/app/channels/telegram/bot.py',
	// LCM retrieval lab (PR #258) — two files still over budget. ``evals.py``
	// is the largest (873 lines: harness + scenarios + answerer + retrievers
	// all in one) and the natural split is into an ``evals/`` package
	// (runner / seeding / answerer / retrievers). ``embeddings.py`` is
	// storage + semantic + RRF; split semantic vs RRF blender.
	// TODO(pawrrtal-lcm-split follow-up): land the two splits and
	// remove this exemption.
	'backend/app/lcm/evals.py',
	'backend/app/lcm/embeddings.py',
	// turn_runner grew past 500 after the active-recall + structured
	// logging work landed on development. The natural split is to
	// extract the post-turn hook orchestration (LCM compact, recall,
	// dreaming trigger) into a sibling ``post_turn_hooks.py``.
	// TODO(pawrrtal-turn-runner-split): land the split and remove.
	'backend/app/channels/turn_runner.py',
	// Block-index plumbing (#371) and regenerate-button threading (#414)
	// grew these files past 500. Each has a documented split plan in the
	// refactor PRs (#394, #403, #409). Exempt until those land.
	'backend/app/models.py',
	'backend/app/providers/opencode_go_provider.py',
	'backend/app/providers/gemini_provider.py',
	'backend/app/channels/_telegram_dispatch.py',
	'backend/app/channels/telegram.py',
	'backend/app/agents/types.py',
];

/** Recursively yield every source file under `dir` that we should check. */
async function* walk(dir) {
	let entries;
	try {
		entries = await fs.readdir(dir, { withFileTypes: true });
	} catch {
		return;
	}

	for (const entry of entries) {
		if (entry.isDirectory()) {
			if (SKIP_DIRECTORIES.has(entry.name)) continue;
			yield* walk(path.join(dir, entry.name));
			continue;
		}
		if (!entry.isFile()) continue;

		const ext = path.extname(entry.name);
		if (!TARGET_EXTENSIONS.has(ext)) continue;
		if (EXEMPT_SUFFIXES.some((suffix) => entry.name.endsWith(suffix))) continue;

		yield path.join(dir, entry.name);
	}
}

/** Count newline characters in `filePath` — cheap proxy for line count. */
async function countLines(filePath) {
	const contents = await fs.readFile(filePath, 'utf8');
	if (contents.length === 0) return 0;
	// `split('\n').length` is one off when the file lacks a trailing newline,
	// but the difference of 1 is irrelevant against a 500-line budget.
	return contents.split('\n').length;
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
		for await (const filePath of walk(absoluteRoot)) {
			const relative = path.relative(REPO_ROOT, filePath);
			if (EXEMPT_PATH_FRAGMENTS.some((fragment) => relative.includes(fragment))) {
				continue;
			}
			const lineCount = await countLines(filePath);
			if (lineCount > MAX_LINES) {
				offenders.push({ relative, lines: lineCount });
			}
		}
	}

	if (offenders.length === 0) {
		console.log(`file-lines: OK (no source files exceed ${MAX_LINES} lines)`);
		return;
	}

	offenders.sort((left, right) => right.lines - left.lines);
	console.error(`file-lines: ${offenders.length} file(s) exceed ${MAX_LINES} lines:\n`);
	for (const offender of offenders) {
		console.error(`  ${offender.lines.toString().padStart(5)}  ${offender.relative}`);
	}
	console.error('\nSplit large files into smaller modules to keep each under the budget.');
	process.exitCode = 1;
}

await main();

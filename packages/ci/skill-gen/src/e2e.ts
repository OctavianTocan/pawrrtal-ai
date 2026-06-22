import type { Dirent } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

/** Collect matching skill files below a directory. */
async function collectFiles(dir: string, prefix = ''): Promise<string[]> {
	let entries: Dirent[];
	try {
		entries = await readdir(dir, { withFileTypes: true });
	} catch {
		return [];
	}

	const results = await Promise.all(
		entries.map((entry): string[] | Promise<string[]> => {
			const relPath = prefix ? `${prefix}/${entry.name}` : entry.name;
			if (entry.isDirectory()) {
				return collectFiles(resolve(dir, entry.name), relPath);
			}
			if (entry.name === 'SKILL.md') {
				return [relPath];
			}
			return [];
		})
	);

	return results.flat();
}

/**
 * Collect every SKILL.md beneath a directory, recursively.
 *
 * @param dir - Root directory to search.
 * @param prefix - Path prefix prepended to results; callers pass nothing at the top level.
 * @returns Paths relative to the root directory (e.g. "coding/SKILL.md").
 */
export function collectSkillFiles(dir: string, prefix = ''): Promise<string[]> {
	return collectFiles(dir, prefix);
}

/**
 * Compare one generated file against its expected fixture, logging any mismatch.
 *
 * @param file - Path of the file relative to both directories.
 * @param expectedDir - Directory holding the expected fixture content.
 * @param actualDir - Directory holding the generated output to verify.
 * @returns True when the file exists in both and the contents match, false otherwise.
 */
export async function compareFile(
	file: string,
	expectedDir: string,
	actualDir: string
): Promise<boolean> {
	const expectedContent = await readFile(resolve(expectedDir, file), 'utf-8');
	const actualPath = resolve(actualDir, file);

	let actualContent: string;
	try {
		actualContent = await readFile(actualPath, 'utf-8');
	} catch {
		console.error(`FAIL: expected file ${file} not found in output`);
		return false;
	}

	if (actualContent !== expectedContent) {
		console.error(`FAIL: ${file} content mismatch`);
		printDiff(expectedContent, actualContent);
		return false;
	}

	return true;
}

/** Print line-by-line differences between expected and actual content to stderr. */
function printDiff(expected: string, actual: string): void {
	const expLines = expected.split('\n');
	const actLines = actual.split('\n');
	const maxLen = Math.max(expLines.length, actLines.length);
	for (let i = 0; i < maxLen; i++) {
		if (expLines[i] !== actLines[i]) {
			if (actLines[i] !== undefined) {
				console.error(`  - ${actLines[i]}`);
			}
			if (expLines[i] !== undefined) {
				console.error(`  + ${expLines[i]}`);
			}
		}
	}
}

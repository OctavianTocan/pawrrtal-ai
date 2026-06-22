import { dirname } from 'node:path';
import type { RawFragment } from './scan';

export interface ParsedSkillFragment {
	/** Skill name from the `name` frontmatter key */
	name: string;
	/** Description from the `description` frontmatter key */
	description: string;
	/** Extra frontmatter lines preserved in generated output */
	extraFrontmatter: string[];
	/** Markdown body after frontmatter */
	body: string;
	/** Source file relative path */
	relativePath: string;
}

const COMMENT_SLASH_RE = /^(\s*)\/\/\s?/;
const COMMENT_HASH_RE = /^(\s*)#\s?/;

/**
 * Strip leading comment characters (`//` or `#`) and an optional single space
 * from each line of a raw fragment block.
 */
function stripComments(lines: string[]): string[] {
	return lines.map((line) => {
		if (line.trimStart().startsWith('//')) {
			return line.replace(COMMENT_SLASH_RE, '$1');
		}
		if (line.trimStart().startsWith('#')) {
			return line.replace(COMMENT_HASH_RE, '$1');
		}
		return line;
	});
}

/**
 * Expand template variables in raw text.
 * - `$$file` -> relative path to the source file
 * - `$$directory` -> relative path to the source file's directory
 *
 * Use `\$$file` or `\$$directory` to produce a literal `$$file` / `$$directory`
 * in the output (the backslash is consumed).
 */
function expandTemplateVars(text: string, relativePath: string): string {
	const relativeDir = dirname(relativePath);
	const dirValue = relativeDir === '.' ? '.' : relativeDir;

	const ESCAPE_DIR = '\0ESCAPED_DIRECTORY\0';
	const ESCAPE_FILE = '\0ESCAPED_FILE\0';

	let result = text.replaceAll('\\$$directory', ESCAPE_DIR).replaceAll('\\$$file', ESCAPE_FILE);

	result = result.replaceAll('$$directory', dirValue).replaceAll('$$file', relativePath);

	// Function replacements avoid JS treating `$$` as an escape in replacement strings.
	result = result
		.replaceAll(ESCAPE_DIR, () => '$$directory')
		.replaceAll(ESCAPE_FILE, () => '$$file');

	return result;
}

/** Find the index of the opening `---` delimiter, skipping leading blank lines. Returns -1 if not found. */
function findOpeningDelimiter(lines: string[]): number {
	for (let i = 0; i < lines.length; i++) {
		const line = lines[i] ?? '';
		if (line.trim() === '---') {
			return i;
		}
		if (line.trim() !== '') {
			return -1;
		}
	}
	return -1;
}

/** Find the index of the closing `---` delimiter after startIdx. Returns -1 if not found. */
function findClosingDelimiter(lines: string[], startIdx: number): number {
	for (let i = startIdx + 1; i < lines.length; i++) {
		const line = lines[i] ?? '';
		if (line.trim() === '---') {
			return i;
		}
	}
	return -1;
}

interface ParsedFrontmatter {
	fields: Record<string, string>;
	extraFrontmatter: string[];
}

/** Remove simple YAML string quotes from scalar field values. */
function unquoteScalar(value: string): string {
	if (
		(value.startsWith('"') && value.endsWith('"')) ||
		(value.startsWith("'") && value.endsWith("'"))
	) {
		return value.slice(1, -1);
	}

	return value;
}

/** Parse required key-value pairs and preserve non-core YAML lines. */
function parseFields(lines: string[], startIdx: number, endIdx: number): ParsedFrontmatter {
	const fields: Record<string, string> = {};
	const extraFrontmatter: string[] = [];

	for (let i = startIdx + 1; i < endIdx; i++) {
		const rawLine = (lines[i] ?? '').trimEnd();
		const line = rawLine.trim();
		if (line === '') {
			continue;
		}

		const colonIdx = line.indexOf(':');
		if (colonIdx === -1) {
			extraFrontmatter.push(rawLine);
			continue;
		}

		const key = line.slice(0, colonIdx).trim();
		const value = unquoteScalar(line.slice(colonIdx + 1).trim());

		if (key === 'name' || key === 'description') {
			fields[key] = value;
			continue;
		}

		extraFrontmatter.push(rawLine);
	}

	return { fields, extraFrontmatter };
}

/** Extract the body after the closing frontmatter delimiter. */
function extractBody(lines: string[], endIdx: number): string {
	const bodyLines = lines.slice(endIdx + 1);
	if (bodyLines.length > 0 && bodyLines[0]?.trim() === '') {
		return bodyLines.slice(1).join('\n');
	}
	return bodyLines.join('\n');
}

/**
 * Parse YAML frontmatter from markdown content.
 * Returns the frontmatter fields and the body after frontmatter.
 */
function parseFrontmatter(content: string): {
	fields: Record<string, string>;
	extraFrontmatter: string[];
	body: string;
} {
	const lines = content.split('\n');

	const startIdx = findOpeningDelimiter(lines);
	if (startIdx === -1) {
		return { fields: {}, extraFrontmatter: [], body: content };
	}

	const endIdx = findClosingDelimiter(lines, startIdx);
	if (endIdx === -1) {
		return { fields: {}, extraFrontmatter: [], body: content };
	}

	const { fields, extraFrontmatter } = parseFields(lines, startIdx, endIdx);
	const body = extractBody(lines, endIdx);

	return { fields, extraFrontmatter, body };
}

/**
 * Resolve a raw skill fragment into its name, description, and markdown body.
 *
 * @param fragment - Raw fragment block extracted from a source file.
 * @returns The parsed skill fragment, or `null` when the block lacks both a
 *   `name` and `description` frontmatter key (such blocks are silently skipped).
 */
export function parseFragment(fragment: RawFragment): ParsedSkillFragment | null {
	const stripped = stripComments(fragment.lines);
	const rawText = stripped.join('\n');
	const expanded = expandTemplateVars(rawText, fragment.relativePath);

	const { fields, extraFrontmatter, body } = parseFrontmatter(expanded);

	if (!fields.name || fields.name.length === 0) {
		return null;
	}

	if (!fields.description || fields.description.length === 0) {
		return null;
	}

	return {
		name: fields.name,
		description: fields.description,
		extraFrontmatter,
		body,
		relativePath: fragment.relativePath,
	};
}

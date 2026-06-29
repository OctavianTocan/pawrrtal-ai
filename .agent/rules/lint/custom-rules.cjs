'use strict';

/**
 * Custom markdownlint rules for claude-rules repository.
 *
 * Validates that every rule file follows the Claude Code frontmatter spec
 * and the structural conventions documented in AGENTS.md.
 *
 * Key markdownlint internals:
 *   - params.lines: file content with frontmatter STRIPPEN (line 0 = first body line)
 *   - params.frontMatterLines: raw frontmatter lines (including --- delimiters)
 *   - params.name: full file path
 *   - params.tokens: parsed markdown AST tokens (body only)
 */

const yamlLight = require('./yaml-light.cjs');
const parseYaml = yamlLight.parse;
const path = require('node:path');

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Parse frontmatter from markdownlint's frontMatterLines param. */
function parseFrontMatterFromParams(frontMatterLines) {
	if (!frontMatterLines || frontMatterLines.length < 2) return null;
	// frontMatterLines[0] = "---", frontMatterLines[last] = "---"
	// Content is everything in between
	const fmText = frontMatterLines.slice(1, -1).join('\n');
	return parseYaml(fmText);
}

/** Check if a file is a rule file (not a top-level doc). */
function isRuleFile(filePath) {
	const basename = path.basename(filePath);
	const nonRuleFiles = ['README.md', 'CHANGELOG.md', 'AGENTS.md', 'CLAUDE.md', 'CLAUDE.local.md'];
	if (nonRuleFiles.includes(basename)) return false;
	// Only .md files in category subdirectories are rules
	// Top-level .md files (other than the ones above) are not rules
	const rel = path.relative(process.cwd(), filePath);
	return rel.includes(path.sep);
}

/** Get the basename without .md extension. */
function stem(filePath) {
	return path.basename(filePath, '.md');
}

// ─── Rule: CC001 — frontmatter-fields ───────────────────────────────────────

module.exports = [
	{
		names: ['CC001', 'frontmatter-fields'],
		description: 'Rule files must have valid YAML frontmatter with name and paths fields',
		tags: ['frontmatter'],
		function: function CC001(params, onError) {
			if (!isRuleFile(params.name)) return;

			const parsed = parseFrontMatterFromParams(params.frontMatterLines);

			if (!parsed) {
				onError({
					lineNumber: 1,
					detail: 'Missing or invalid frontmatter. Expected:\\n---\\nname: slug\\npaths: ["globs"]\\n---',
				});
				return;
			}

			// name: required, must be kebab-case matching the filename
			if (!parsed.name) {
				onError({
					lineNumber: 1,
					detail: 'Missing "name" field in frontmatter.',
				});
			} else if (!/^[a-z][a-z0-9-]*$/.test(parsed.name)) {
				onError({
					lineNumber: 1,
					detail: `"name" must be kebab-case (lowercase, digits, hyphens). Got: "${parsed.name}"`,
				});
			}

			// name should match filename (without .md)
			const basename = stem(params.name);
			if (parsed.name && parsed.name !== basename) {
				onError({
					lineNumber: 1,
					detail: `"name" ("${parsed.name}") should match filename ("${basename}")`,
				});
			}

			// paths: required, must be array of glob strings
			if (!parsed.paths) {
				onError({
					lineNumber: 1,
					detail: 'Missing "paths" field. This is the official Claude Code frontmatter field for scoping rules to file patterns.',
				});
			} else if (!Array.isArray(parsed.paths)) {
				onError({
					lineNumber: 1,
					detail: `"paths" must be an array of glob strings. Got: ${typeof parsed.paths}`,
				});
			} else {
				for (let i = 0; i < parsed.paths.length; i++) {
					if (typeof parsed.paths[i] !== 'string') {
						onError({
							lineNumber: 1,
							detail: `paths[${i}] must be a string, got ${typeof parsed.paths[i]}`,
						});
					}
				}
			}

			// Disallow legacy/invalid fields
			const invalidFields = ['triggers', 'description', 'globs', 'alwaysApply'];
			for (const field of invalidFields) {
				if (parsed[field] !== undefined) {
					onError({
						lineNumber: 1,
						detail: `Legacy field "${field}" found in frontmatter. Remove it. Only "name" and "paths" are valid.`,
					});
				}
			}
		},
	},

	// ─── Rule: CC002 — required-sections ────────────────────────────────────

	{
		names: ['CC002', 'required-sections'],
		description: 'Rule files must contain ## Verify and ## Patterns sections',
		tags: ['structure'],
		function: function CC002(params, onError) {
			if (!isRuleFile(params.name)) return;

			const tokens = params.tokens;
			const headings = tokens.filter((t) => t.type === 'heading_open' && t.tag === 'h2');

			const headingTexts = headings.map((h) => {
				const idx = tokens.indexOf(h) + 1;
				return tokens[idx] ? tokens[idx].content.trim() : '';
			});

			const required = ['Verify', 'Patterns'];
			for (const section of required) {
				if (!headingTexts.some((t) => t === section)) {
					onError({
						lineNumber: 1,
						detail: `Missing "## ${section}" section. Every rule must have ${required.map((s) => `## ${s}`).join(' and ')}.`,
					});
				}
			}
		},
	},

	// ─── Rule: CC003 — heading-is-descriptive ───────────────────────────────

	{
		names: ['CC003', 'heading-is-descriptive'],
		description:
			'The H1 heading should be a descriptive sentence, not a bare echo of the filename',
		tags: ['structure'],
		function: function CC003(params, onError) {
			if (!isRuleFile(params.name)) return;

			const parsed = parseFrontMatterFromParams(params.frontMatterLines);
			if (!parsed?.name) return;

			const lines = params.lines;
			// Find H1 line (first line starting with #)
			for (let i = 0; i < lines.length; i++) {
				if (lines[i].startsWith('# ')) {
					const heading = lines[i].replace(/^# /, '').trim();
					// If heading is identical to name (kebab-case slug), that's bad
					if (heading === parsed.name) {
						onError({
							lineNumber: i + 1,
							detail: `H1 heading "${heading}" is just the filename slug. Use a descriptive sentence instead.`,
						});
					}
					// If heading is just Title Case of the slug, also bad
					const titleCased = parsed.name
						.split('-')
						.map((w) => w.charAt(0).toUpperCase() + w.slice(1))
						.join(' ');
					if (heading === titleCased) {
						onError({
							lineNumber: i + 1,
							detail: `H1 heading "${heading}" is just Title Case of the filename. Use a descriptive sentence instead.`,
						});
					}
					break;
				}
			}
		},
	},
];

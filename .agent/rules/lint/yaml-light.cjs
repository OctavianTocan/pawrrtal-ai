'use strict';

/**
 * Lightweight YAML parser for frontmatter.
 * Handles the flat key-value pairs and single-level arrays we use.
 * No external dependencies.
 */

const KEY_VALUE_PATTERN = /^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)/;
const LIST_ITEM_PATTERN = /^\s*-\s/;

function isQuoted(value) {
	return (
		(value.startsWith('"') && value.endsWith('"')) ||
		(value.startsWith("'") && value.endsWith("'"))
	);
}

function stripQuotes(value) {
	return isQuoted(value) ? value.slice(1, -1) : value;
}

function parseBlockArray(lines, startIndex) {
	const items = [];
	let index = startIndex;

	while (index < lines.length && LIST_ITEM_PATTERN.test(lines[index])) {
		const item = lines[index].replace(/^\s*-\s*/, '').trim();
		items.push(stripQuotes(item));
		index++;
	}

	return { items, nextIndex: index };
}

function splitInlineArrayItems(inner) {
	const items = [];
	let current = '';
	let quoteChar = '';

	for (const ch of inner) {
		if (quoteChar) {
			quoteChar = ch === quoteChar ? '' : quoteChar;
			current += ch;
		} else if (ch === '"' || ch === "'") {
			quoteChar = ch;
			current += ch;
		} else if (ch === ',') {
			items.push(stripQuotes(current.trim()));
			current = '';
		} else {
			current += ch;
		}
	}

	if (current.trim()) {
		items.push(stripQuotes(current.trim()));
	}

	return items.filter(Boolean);
}

function parseInlineValue(value) {
	if (isQuoted(value)) return value.slice(1, -1);
	if (value === 'true') return true;
	if (value === 'false') return false;
	if (value.startsWith('[') && value.endsWith(']')) {
		return splitInlineArrayItems(value.slice(1, -1));
	}
	if (!Number.isNaN(Number(value))) return Number(value);
	return value;
}

function parse(text) {
	const result = {};
	const lines = text.split('\n');
	let index = 0;

	while (index < lines.length) {
		const line = lines[index];
		const match =
			line.trim() && !LIST_ITEM_PATTERN.test(line) ? line.match(KEY_VALUE_PATTERN) : null;

		if (!match) {
			index++;
			continue;
		}

		const key = match[1];
		const value = match[2].trim();

		if (value === '') {
			const { items, nextIndex } = parseBlockArray(lines, index + 1);
			result[key] = items.length > 0 ? items : null;
			index = items.length > 0 ? nextIndex : index + 1;
		} else {
			result[key] = parseInlineValue(value);
			index++;
		}
	}

	return result;
}

module.exports = { parse };

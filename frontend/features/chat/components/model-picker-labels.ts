/**
 * Display labels for model-catalog `host` and `vendor` slugs.
 *
 * @fileoverview Mirrors the backend's `app.core.providers.labels`
 * module. Two small maps don't justify an API round-trip; if either
 * side adds a new entry, the new slug falls back to itself instead
 * of throwing so the picker keeps rendering.
 */

const HOST_LABELS: Readonly<Record<string, string>> = {
	'agent-sdk': 'Anthropic Agent SDK',
	'google-ai': 'Gemini API',
	litellm: 'LiteLLM',
	'opencode-go': 'OpenCode Go',
	xai: 'xAI',
};

const VENDOR_LABELS: Readonly<Record<string, string>> = {
	anthropic: 'Anthropic',
	google: 'Google',
	moonshot: 'Moonshot',
	openai: 'OpenAI',
	xai: 'xAI',
	zai: 'Z.AI',
};

/**
 * Return the display label for a host wire-slug.
 *
 * @param slug - The host's wire-form slug (e.g. `'agent-sdk'`).
 * @returns The display label, or the slug itself when unknown.
 */
export function hostLabel(slug: string): string {
	return HOST_LABELS[slug] ?? slug;
}

/**
 * Return the display label for a vendor wire-slug.
 *
 * @param slug - The vendor's wire-form slug (e.g. `'zai'`).
 * @returns The display label, or the slug itself when unknown.
 */
export function vendorLabel(slug: string): string {
	return VENDOR_LABELS[slug] ?? slug;
}

/**
 * Display labels for model-catalog `host` and `vendor` slugs.
 *
 * @fileoverview Mirrors the backend's `app.core.providers.labels`
 * module. Two small maps don't justify an API round-trip; if either
 * side adds a new entry, the new slug falls back to itself instead
 * of throwing so the picker keeps rendering.
 */

/** Map from host wire-slug to user-facing display string. Mirrors backend `app.core.providers.labels.HOST_LABELS`. */
const HOST_LABELS = {
	'agent-sdk': 'Anthropic Agent SDK',
	'agy-api': 'Antigravity API',
	'gemini-cli': 'Gemini CLI',
	'google-ai': 'Gemini API',
	litellm: 'LiteLLM',
	'opencode-go': 'OpenCode Go',
	'openai-codex': 'Codex SDK',
	xai: 'xAI',
} as const satisfies Record<string, string>;

/** Map from vendor wire-slug to user-facing display string. Mirrors backend `app.core.providers.labels.VENDOR_LABELS`. */
const VENDOR_LABELS = {
	alibaba: 'Alibaba',
	anthropic: 'Anthropic',
	deepseek: 'DeepSeek',
	google: 'Google',
	minimax: 'MiniMax',
	moonshot: 'Moonshot',
	openai: 'OpenAI',
	xai: 'xAI',
	xiaomi: 'Xiaomi',
	zai: 'Z.AI',
} as const satisfies Record<string, string>;

/**
 * Return the display label for a host wire-slug.
 *
 * @param slug - The host's wire-form slug (e.g. `'agent-sdk'`).
 * @returns The display label, or the slug itself when unknown.
 */
export function hostLabel(slug: string): string {
	return (HOST_LABELS as Record<string, string>)[slug] ?? slug;
}

/**
 * Return the display label for a vendor wire-slug.
 *
 * @param slug - The vendor's wire-form slug (e.g. `'zai'`).
 * @returns The display label, or the slug itself when unknown.
 */
export function vendorLabel(slug: string): string {
	return (VENDOR_LABELS as Record<string, string>)[slug] ?? slug;
}

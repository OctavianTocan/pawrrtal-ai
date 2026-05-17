/**
 * Single source of truth for the personalization profile that the
 * onboarding flow collects and the Settings → Personalization section
 * edits. Persisted to localStorage under `pawrrtal:personalization` so both
 * surfaces read/write the same shape.
 *
 * Backend wiring is deferred — once the agent factory threads custom
 * instructions through the system prompt, the backend will read the
 * same fields from `user_preferences` and the localStorage cache becomes
 * a draft buffer until save.
 *
 * @fileoverview Shared personalization profile + load/save helpers.
 */

/** localStorage key — never rename without a migration. */
export const PERSONALIZATION_STORAGE_KEY = 'pawrrtal:personalization';

/** Personality preset IDs the onboarding flow + settings dropdown share. */
export const PERSONALITY_OPTIONS = [
	{
		id: 'goose',
		label: 'Goose',
		summary: 'Direct, opinionated, and genuinely helpful — no corporate fluff.',
		traits: ['Direct', 'Opinionated', 'Competent'],
	},
	{
		id: 'sharp-coworker',
		label: 'Sharp Co-worker',
		summary: 'Direct, decisive, and gets things done. Treats you like a peer.',
		traits: ['Direct', 'Opinionated', 'Efficient'],
	},
	{
		id: 'honest-coach',
		label: 'Honest Coach',
		summary: 'Tells you the truth even when it stings. Pushes you to do better.',
		traits: ['Candid', 'Challenging', 'High-standards'],
	},
	{
		id: 'thorough-analyst',
		label: 'Thorough Analyst',
		summary: 'Methodical and comprehensive. Shows its work, leaves nothing out.',
		traits: ['Detailed', 'Structured', 'Careful'],
	},
	{
		id: 'relentless-executor',
		label: 'Relentless Executor',
		summary: 'Bias to action. Closes loops fast, never leaves work half-done.',
		traits: ['Action-first', 'Decisive', 'Fast'],
	},
] as const satisfies ReadonlyArray<{
	id: string;
	label: string;
	summary: string;
	traits: readonly string[];
}>;

/** Union of all valid personality IDs. */
export type PersonalityId = (typeof PERSONALITY_OPTIONS)[number]['id'];

/** Messaging channels the onboarding flow can connect (visual-only today). */
export const MESSAGING_CHANNELS = [
	{ id: 'slack', label: 'Slack', color: '#4A154B' },
	{ id: 'telegram', label: 'Telegram', color: '#0088cc' },
	{ id: 'whatsapp', label: 'WhatsApp', color: '#25D366' },
	{ id: 'imessage', label: 'iMessage', color: '#34C759' },
] as const satisfies ReadonlyArray<{ id: string; label: string; color: string }>;

/** Stable IDs for the messaging channels above. */
export type MessagingChannelId = (typeof MESSAGING_CHANNELS)[number]['id'];

/**
 * Profile assembled across the onboarding flow + edited from the
 * Personalization settings section. All fields are optional so partial
 * progress (skip step 2, etc) round-trips cleanly through localStorage.
 */
export interface PersonalizationProfile {
	/** Display name from step 1. */
	name?: string;
	/** Company / project URL. */
	companyWebsite?: string;
	/** Optional LinkedIn profile URL. */
	linkedin?: string;
	/** Free-form role label ("Founder", "Engineering"). */
	role?: string;
	/** Goal chips selected in step 1. */
	goals?: string[];
	/** Pasted ChatGPT context blob from step 2. */
	chatgptContext?: string;
	/** Personality preset chosen in step 3. */
	personality?: PersonalityId;
	/** Channels the user clicked Connect on in step 4. Visual only. */
	connectedChannels?: MessagingChannelId[];
	/** Custom instructions surfaced in the Personalization settings section. */
	customInstructions?: string;
	/**
	 * Optional URL of a self-hosted Pawrrtal backend, e.g.
	 * `https://pawrrtal.mycompany.com`. When set the frontend will prefer
	 * this over the default same-origin API base. Empty or absent means
	 * "use the hosted / same-origin server".
	 */
	remoteServerUrl?: string;
}

/** Fallback used when nothing is persisted yet. */
export const EMPTY_PROFILE: PersonalizationProfile = {
	goals: [],
	connectedChannels: [],
};

/**
 * Read the persisted personalization profile from localStorage.
 *
 * Returns `EMPTY_PROFILE` on SSR, parse failures, or first-run. The fallback
 * preserves the empty array shape so consumers can iterate `goals` /
 * `connectedChannels` without nil-guards.
 */
export function loadPersonalizationProfile(): PersonalizationProfile {
	if (typeof window === 'undefined') return EMPTY_PROFILE;
	try {
		const raw = window.localStorage.getItem(PERSONALIZATION_STORAGE_KEY);
		if (!raw) return EMPTY_PROFILE;
		const parsed = JSON.parse(raw) as PersonalizationProfile;
		return { ...EMPTY_PROFILE, ...parsed };
	} catch {
		return EMPTY_PROFILE;
	}
}

/**
 * Write the personalization profile to localStorage.
 *
 * Wrapped in try/catch because storage writes throw in private browsing
 * and when quota is exceeded — we silently swallow because the profile
 * is non-critical UX state, not data the user expects to never lose.
 */
export function savePersonalizationProfile(profile: PersonalizationProfile): void {
	if (typeof window === 'undefined') return;
	try {
		window.localStorage.setItem(PERSONALIZATION_STORAGE_KEY, JSON.stringify(profile));
	} catch {
		/* private browsing / quota — swallow */
	}
}

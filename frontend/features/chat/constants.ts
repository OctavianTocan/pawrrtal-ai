/**
 * Centralized constants for the chat feature.
 *
 * Houses the canonical set of values, defaults, and `localStorage` keys used
 * across the chat surface (container, composer wiring, host-local
 * footerActions). Co-locating them here prevents key drift, makes it trivial
 * to audit what we persist client side, and gives one obvious place to look
 * when adding or renaming a key.
 *
 * Conventions:
 * - `localStorage` keys are namespaced with `chat-composer:` so they don't
 *   collide with sidebar / nav / future feature keys in the same origin.
 * - `as const` tuples are used for enum-like sets so callers can both narrow
 *   types at compile time and validate persisted strings at runtime.
 */

// ─── reasoning levels ──────────────────────────────────────────────────────

/** Reasoning levels exposed in the picker. */
export const CHAT_REASONING_LEVELS = ['low', 'medium', 'high', 'extra-high'] as const;

/** Narrow union of every reasoning level. */
export type ChatReasoningLevel = (typeof CHAT_REASONING_LEVELS)[number];

// ─── localStorage keys ─────────────────────────────────────────────────────

/**
 * Single source of truth for every `localStorage` key the chat feature owns.
 *
 * Use this object rather than inline string literals so renames stay safe and
 * the full set of persisted keys is visible at a glance.
 */
export const CHAT_STORAGE_KEYS = {
	/** User's most recently selected reasoning level. */
	selectedReasoning: 'chat-composer:selected-reasoning-level',
	/** Whether the Plan-mode toggle is currently visible in the toolbar. */
	planModeVisible: 'chat-composer:plan-mode-visible',
	/** Active safety / auto-review permission mode. */
	safetyMode: 'chat-composer:safety-mode',
} as const;

/** Union of every recognized chat `localStorage` key. */
export type ChatStorageKey = (typeof CHAT_STORAGE_KEYS)[keyof typeof CHAT_STORAGE_KEYS];

// ─── defaults ──────────────────────────────────────────────────────────────

/**
 * Default reasoning level used when nothing is persisted yet.
 *
 * The default model is the FIRST entry the backend catalog returns
 * (`GET /api/v1/models`), resolved in-session and not persisted, so there
 * is no `DEFAULT_CHAT_MODEL_ID` constant or `selectedModelId` storage key
 * here — see `frontend/features/chat/hooks/use-chat-models.ts` and
 * `ChatContainer`'s `useSelectedChatModel`.
 */
export const DEFAULT_REASONING_LEVEL: ChatReasoningLevel = 'medium';

/**
 * Default Plan-mode visibility for a fresh chat session. Off by default so a
 * brand-new conversation doesn't start in Plan mode — the user opts in via
 * Shift+Tab and the choice is then persisted.
 */
export const DEFAULT_PLAN_MODE_VISIBLE = false;

// ─── safety-mode enum ──────────────────────────────────────────────────────

/**
 * Identifiers for the safety / auto-review permissions exposed in the
 * composer toolbar. `as const` so the {@link SafetyMode} union and the
 * runtime guard are derived from one source of truth.
 */
export const SAFETY_MODES = [
	'default-permissions',
	'auto-review',
	'full-access',
	'custom',
] as const;

/** Available safety / auto-review permission modes. */
export type SafetyMode = (typeof SAFETY_MODES)[number];

/** Default selection — matches the previously hardcoded "Auto-review" entry. */
export const DEFAULT_SAFETY_MODE: SafetyMode = 'auto-review';

/**
 * Display order for the safety-mode dropdown (top → bottom).
 * Mirrors SAFETY_MODES but is explicit so future reorders are intentional.
 */
export const SAFETY_MODE_ORDER: SafetyMode[] = [
	'default-permissions',
	'auto-review',
	'full-access',
	'custom',
];

/**
 * "Advanced" modes — the dropdown renders a separator ABOVE the first item in
 * this set so users see a clear boundary between safe and dangerous choices.
 */
export const SAFETY_MODE_ADVANCED: ReadonlySet<SafetyMode> = new Set<SafetyMode>([
	'full-access',
	'custom',
]);

// ─── miscellaneous chat-container constants ────────────────────────────────

/** Maximum length for a sidebar-safe fallback conversation title. */
export const FALLBACK_TITLE_MAX_LENGTH = 80;

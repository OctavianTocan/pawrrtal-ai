/**
 * Base URL for all API requests.
 * Determined from NEXT_PUBLIC_API_URL environment variable.
 *
 * Default targets the local FastAPI dev server on `http://localhost:8000`.
 * In production (Vercel) the env var must be set to the deployed API origin.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * Backend API key for the X-Pawrrtal-Key header.
 *
 * Two sources, resolved at runtime (client-side precedence order):
 *   1. localStorage `pawrrtal:backend-config` — set via the Settings page when
 *      a user points at their own backend instance (URL + key stored together).
 *   2. NEXT_PUBLIC_BACKEND_API_KEY build-time env var — baked into the demo
 *      build so the demo instance works out-of-the-box without any config.
 *
 * When neither is set the header is omitted, which is correct for local dev
 * (backend has no BACKEND_API_KEY configured either).
 */
const BACKEND_CONFIG_STORAGE_KEY = 'pawrrtal:backend-config';
export const BACKEND_CONFIG_CHANGED_EVENT = 'pawrrtal:backend-config-changed';

export interface BackendConfig {
	url: string;
	apiKey: string;
}

function readStoredBackendConfig(): BackendConfig | null {
	if (typeof window === 'undefined') {
		return null;
	}
	try {
		const raw = window.localStorage.getItem(BACKEND_CONFIG_STORAGE_KEY);
		if (!raw) {
			return null;
		}
		const parsed = JSON.parse(raw) as Partial<BackendConfig>;
		return {
			url: parsed.url ?? '',
			apiKey: parsed.apiKey ?? '',
		};
	} catch {
		return null;
	}
}

function normalizeBackendConfigUrl(url: string): string {
	if (!url.trim()) {
		return API_BASE_URL;
	}
	try {
		const parsed = new URL(url);
		return parsed.toString();
	} catch {
		return url.trim();
	}
}

function readBackendConfig(): BackendConfig {
	const buildTimeKey = process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? '';
	const defaults: BackendConfig = { url: API_BASE_URL, apiKey: buildTimeKey };
	const stored = readStoredBackendConfig();
	if (stored) {
		return stored;
	}
	return defaults;
}

/**
 * True when the runtime backend config has been explicitly configured in this
 * browser profile. This is the authoritative readiness signal for onboarding.
 */
export function hasBackendConfig(): boolean {
	const config = readStoredBackendConfig();
	return Boolean(config?.url && config.url.trim());
}

/** Stable identifier for the active backend target. */
export function getBackendConfigFingerprint(): string {
	const { url, apiKey } = readBackendConfig();
	const normalizedUrl = normalizeBackendConfigUrl(url);
	return `${normalizedUrl}::${stableConfigKey(apiKey)}`;
}

function stableConfigKey(apiKey: string): string {
	if (!apiKey) {
		return 'key:none';
	}
	let hash = 5381;
	for (let i = 0; i < apiKey.length; i += 1) {
		hash = (hash * 33) ^ apiKey.charCodeAt(i);
	}
	return `key:${hash >>> 0}`;
}

function emitBackendConfigChange(): void {
	if (typeof window === 'undefined') {
		return;
	}
	window.dispatchEvent(new Event(BACKEND_CONFIG_CHANGED_EVENT));
}

/** Persist a new backend config (URL + API key) to localStorage. */
export function saveBackendConfig(config: BackendConfig): void {
	try {
		window.localStorage.setItem(BACKEND_CONFIG_STORAGE_KEY, JSON.stringify(config));
		emitBackendConfigChange();
	} catch {
		/* quota / private browsing — ignore */
	}
}

/** Clear the runtime backend config override (reverts to build-time defaults). */
function clearBackendConfig(): void {
	try {
		window.localStorage.removeItem(BACKEND_CONFIG_STORAGE_KEY);
		emitBackendConfigChange();
	} catch {
		/* ignore */
	}
}

/**
 * Drop-in replacement for `fetch` that:
 *   - Prepends `API_BASE_URL` (or the runtime URL from localStorage) to the path.
 *   - Adds the `X-Pawrrtal-Key` header when an API key is configured.
 *
 * Use this for every backend request instead of calling `fetch` directly so the
 * key header is applied consistently across the entire frontend.
 *
 * @example
 *   const res = await apiFetch('/api/v1/chat', { method: 'POST', body: JSON.stringify(msg) });
 */
export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
	const { url: baseUrl, apiKey } = readBackendConfig();
	// Only wrap headers in a Headers object when we actually need to inject
	// X-Pawrrtal-Key.  When no key is configured (local dev, tests) we pass
	// init through unchanged so callers that stub `fetch` get back the same
	// plain-object headers they supplied — keeping test assertions simple.
	if (!apiKey) {
		return fetch(`${baseUrl}${path}`, init);
	}
	const headers = new Headers(init?.headers);
	headers.set('X-Pawrrtal-Key', apiKey);
	return fetch(`${baseUrl}${path}`, { ...init, headers });
}

/**
 * API endpoint definitions for frontend requests.
 * Organized by logical service areas. Use curried functions for endpoints with path params,
 * and plain string properties for static endpoints.
 */
export const API_ENDPOINTS = {
	autocomplete: '/api/v1/completions/autocomplete',
	/** Endpoints related to chat functionality */
	chat: {
		/**
		 * Chat streaming endpoint.
		 * @returns `/api/v1/chat`
		 */
		messages: '/api/v1/chat',
		models: '/api/v1/models',
	},
	/** Endpoints for conversation management */
	conversations: {
		/**
		 * Get an individual conversation by ID.
		 * @param id - Conversation ID
		 * @returns `/api/v1/conversations/${id}`
		 */
		get: (id: string) => `/api/v1/conversations/${id}`,
		/**
		 * Get the messages for a conversation by ID.
		 * @param id - Conversation ID
		 * @returns `/api/v1/conversations/${id}/messages`
		 */
		getMessages: (id: string) => `/api/v1/conversations/${id}/messages`,
		/**
		 * Create a conversation.
		 * @returns `/api/v1/conversations`
		 */
		create: (id: string) => `/api/v1/conversations/${id}`,
		/**
		 * Update conversation metadata.
		 * @param id - Conversation ID
		 * @returns `/api/v1/conversations/${id}`
		 */
		update: (id: string) => `/api/v1/conversations/${id}`,
		/**
		 * Delete a conversation.
		 * @param id - Conversation ID
		 * @returns `/api/v1/conversations/${id}`
		 */
		delete: (id: string) => `/api/v1/conversations/${id}`,
		list: '/api/v1/conversations',
		/**
		 * Generate a conversation title.
		 * @param id - Conversation ID
		 * @returns `/api/v1/conversations/${id}/title`
		 */
		generateTitle: (id: string, firstMessage: string) =>
			`/api/v1/conversations/${id}/title?first_message=${encodeURIComponent(firstMessage)}`,
	},
	/** Endpoints for authentication actions */
	auth: {
		/**
		 * Login endpoint.
		 * @returns `/auth/jwt/login`
		 */
		login: '/auth/jwt/login',
		/**
		 * Dev-only admin login shortcut.
		 * @returns `/auth/dev-login`
		 */
		devLogin: '/auth/dev-login',
		/**
		 * Register endpoint.
		 * @returns `/auth/register`
		 */
		register: '/auth/register',
		/**
		 * Logout endpoint.
		 * @returns `/auth/logout`
		 */
		logout: '/auth/logout',
		/**
		 * Get current user info (FastAPI-Users router mounted at `/api/v1/users`).
		 * @returns `/api/v1/users/me`
		 */
		me: '/api/v1/users/me',
	},
	/** Endpoints related to user management */
	users: {
		/**
		 * Get all users.
		 * @returns `/api/v1/users`
		 */
		get: '/api/v1/users',
	},
	/** Endpoints for session management */
	session: {
		/**
		 * Get session info.
		 * @returns `/session`
		 */
		get: '/session',
	},
	/** Endpoints for token management */
	token: {
		/**
		 * Get token info.
		 * @returns `/token`
		 */
		get: '/token',
	},
	/** Speech-to-text proxy endpoints (xAI behind the backend). */
	stt: {
		/**
		 * Transcribe an uploaded audio blob via the xAI STT proxy.
		 * @returns `/api/v1/stt`
		 */
		transcribe: '/api/v1/stt',
	},
	/** Personalization wizard (home-page modal) endpoints. */
	personalization: {
		/** Read the authenticated user's personalization profile. */
		get: '/api/v1/personalization',
		/** Replace the authenticated user's personalization profile. */
		put: '/api/v1/personalization',
	},
	/** Project (sidebar grouping) endpoints. */
	projects: {
		/**
		 * List every project owned by the user.
		 * @returns `/api/v1/projects`
		 */
		list: '/api/v1/projects',
		/** Create a new project. */
		create: '/api/v1/projects',
		/**
		 * Update (rename) a project by ID.
		 * @param id - Project ID
		 */
		update: (id: string) => `/api/v1/projects/${id}`,
		/**
		 * Delete a project by ID. Linked conversations are unlinked, not deleted.
		 * @param id - Project ID
		 */
		delete: (id: string) => `/api/v1/projects/${id}`,
	},
	/** Workspace file-system API (backs the Knowledge → My Files surface). */
	workspaces: {
		/** List all workspaces owned by the current user. */
		list: '/api/v1/workspaces',
		/**
		 * Flat file-tree for a workspace.
		 * @param id - Workspace UUID
		 */
		tree: (id: string) => `/api/v1/workspaces/${id}/tree`,
		/**
		 * Read a single file from a workspace.
		 * @param id   - Workspace UUID
		 * @param path - Workspace-relative POSIX path (e.g. `memory/note.md`)
		 */
		file: (id: string, path: string) => `/api/v1/workspaces/${id}/files/${path}`,
		/**
		 * Write (create or replace) a file inside a workspace.
		 * @param id   - Workspace UUID
		 * @param path - Workspace-relative POSIX path
		 */
		writeFile: (id: string, path: string) => `/api/v1/workspaces/${id}/files/${path}`,
		/**
		 * Delete a file from a workspace.
		 * @param id   - Workspace UUID
		 * @param path - Workspace-relative POSIX path
		 */
		deleteFile: (id: string, path: string) => `/api/v1/workspaces/${id}/files/${path}`,
		/**
		 * Per-workspace encrypted env-var overrides.
		 *
		 * Backed by `backend/app/api/workspace_env.py`. The path was workspace_id-keyed
		 * in May 2026 (see ADR
		 * `frontend/content/docs/handbook/decisions/2026-05-15-plugin-system-and-notion-integration.mdx`);
		 * the legacy `/api/v1/workspace/env` shape was removed at the same time.
		 *
		 * @param id - Workspace UUID
		 */
		env: (id: string) => `/api/v1/workspaces/${id}/env`,
		/**
		 * Delete a single env-var override for a workspace.
		 * @param id  - Workspace UUID
		 * @param key - Override key (one of `WORKSPACE_ENV_KEY_IDS`)
		 */
		envKey: (id: string, key: string) => `/api/v1/workspaces/${id}/env/${key}`,
		/** Read onboarding readiness (default workspace existence + metadata). */
		onboardingStatus: '/api/v1/workspaces/onboarding-status',
	},
	/** Third-party messaging channels (Telegram today; more later). */
	channels: {
		/** List every channel binding owned by the authenticated user. */
		list: '/api/v1/channels',
		/** Issue a fresh one-time Telegram link code. */
		telegramLink: '/api/v1/channels/telegram/link',
		/** Drop the user's Telegram binding (idempotent). */
		telegramUnlink: '/api/v1/channels/telegram/link',
	},
} as const;

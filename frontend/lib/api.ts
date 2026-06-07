/**
 * Browser API requests are always same-origin.
 *
 * Local development keeps the familiar split: Next.js serves the browser on
 * `localhost:3000` and rewrites `/api/v1`, `/auth`, and `/users` to the
 * backend on `127.0.0.1:8000`. Cloudflared uses the same URL shape at the
 * edge, routing those paths directly to FastAPI and all other paths to Next.
 */

function buildApiUrl(path: string): string {
	if (/^https?:\/\//.test(path)) {
		return path;
	}
	return path.startsWith('/') ? path : `/${path}`;
}

/** Normalize a browser API path for same-origin requests. */
export function getBrowserApiUrl(path: string): string {
	return buildApiUrl(path);
}

/**
 * Drop-in replacement for `fetch` that:
 *   - Normalizes relative API paths to a leading slash.
 *   - Keeps absolute URLs untouched for rare explicit navigation/probe cases.
 *
 * Use this for every backend request instead of calling `fetch` directly so the
 * browser/runtime shape stays the same across localhost and Cloudflared.
 *
 * @example
 *   const res = await apiFetch('/api/v1/chat', { method: 'POST', body: JSON.stringify(msg) });
 */
export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
	return fetch(buildApiUrl(path), init);
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
		/** Plugin snapshot and enablement for a workspace. */
		plugins: (id: string) => `/api/v1/workspaces/${id}/plugins`,
		/**
		 * Enable or disable one plugin for a workspace.
		 * @param id       - Workspace UUID
		 * @param pluginId - Plugin id
		 */
		plugin: (id: string, pluginId: string) =>
			`/api/v1/workspaces/${id}/plugins/${encodeURIComponent(pluginId)}`,
		/**
		 * Set the preferred capability for a plugin slot.
		 * @param id     - Workspace UUID
		 * @param slotId - Slot id
		 */
		pluginSlot: (id: string, slotId: string) =>
			`/api/v1/workspaces/${id}/plugins/slots/${encodeURIComponent(slotId)}`,
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

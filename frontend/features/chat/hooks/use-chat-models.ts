import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { z } from 'zod';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';

/**
 * Query key used by {@link useChatModels} and any cache mutator that
 * needs to invalidate the catalog.
 */
const CHAT_MODELS_QUERY_KEY = 'models' as const;

/** One entry from `GET /api/v1/models`. */
export interface ChatModelOption {
	/** Canonical wire form: `host:vendor/model` (e.g. `agent-sdk:anthropic/claude-sonnet-4-6`). */
	id: string;
	/** Where the model runs (e.g. `agent-sdk`, `google-ai`). */
	host: string;
	/** Vendor segment of the canonical ID (e.g. `anthropic`, `google`, `openai`). */
	vendor: string;
	/** Vendor's own slug (e.g. `claude-sonnet-4-6`). */
	model: string;
	/** Long display name shown in the picker. */
	display_name: string;
	/** Short label for mobile / compact contexts. */
	short_name: string;
	/** Marketing-style description rendered under the model name. */
	description: string;
}

/** Return shape for {@link useChatModels}. */
export interface UseChatModelsResult {
	/** Catalog entries; empty array while the request is in flight. */
	models: readonly ChatModelOption[];
	/**
	 * The first catalog entry: the pre-selected model for a fresh session.
	 * `null` while loading or when the catalog is empty.
	 */
	default: ChatModelOption | null;
	/** True until the first response (success or error) lands. */
	isLoading: boolean;
	/** True when the model catalog request failed or returned an invalid payload. */
	isError: boolean;
	/** True when at least one valid model row is available. */
	hasCatalog: boolean;
	/** Latest fetch / validation error, or `null` when healthy. */
	error: Error | null;
}

/**
 * Zod schema for one catalog entry — must stay in sync with the backend
 * `ChatModelOption` Pydantic model. Boundary validation per the
 * `validate-response-shape-at-boundary` rule.
 */
const ModelOptionSchema = z.object({
	id: z.string(),
	host: z.string(),
	vendor: z.string(),
	model: z.string(),
	display_name: z.string(),
	short_name: z.string(),
	description: z.string(),
});

/** Zod schema for the `GET /api/v1/models` response envelope. */
const ModelsResponseSchema = z.object({
	models: z.array(z.unknown()),
});

/** Parse one catalog entry and log a warning when its shape is unexpected. */
function parseCatalogModel(entry: unknown, index: number): ChatModelOption | null {
	const result = ModelOptionSchema.safeParse(entry);
	if (result.success) {
		return result.data;
	}
	if (process.env.NODE_ENV !== 'production') {
		console.warn(
			`Model catalog row #${index} was ignored due to schema mismatch:`,
			result.error.format()
		);
	}
	return null;
}

/**
 * Fetches the backend model catalog via TanStack Query.
 *
 * `staleTime: Infinity` keeps the catalog cached for the session.
 * `GET /api/v1/models` exposes an ETag and `Cache-Control:
 * private, must-revalidate`, so the rare revalidation (e.g. on
 * window focus when the cache is later invalidated) is cheap.
 *
 * This hook does **not** use {@link useAuthedQuery} because the
 * shared helper has no `validate` hook for Zod parsing — we call
 * `useAuthedFetch` directly inside the `queryFn` and run the parse
 * there, mirroring the boundary-validation pattern from
 * `frontend/hooks/get-conversations.ts`.
 *
 * @returns Catalog data, the first entry as the fresh-session default,
 *   loading flag, and the latest error (or `null` while healthy).
 */
export function useChatModels(): UseChatModelsResult {
	const authedFetch = useAuthedFetch();

	const query = useQuery<{ models: ChatModelOption[] }>({
		queryKey: [CHAT_MODELS_QUERY_KEY],
		staleTime: Number.POSITIVE_INFINITY,
		queryFn: async (): Promise<{ models: ChatModelOption[] }> => {
			// Caching is disabled by default.
			const response = await authedFetch(API_ENDPOINTS.chat.models);

			if (response.status === 304 || response.status === 204) {
				throw new Error(`Model catalog response returned status ${response.status}`);
			}

			const raw: unknown = await response.json();
			const parsed = ModelsResponseSchema.parse(raw);
			const models = parsed.models
				.map((entry, index) => parseCatalogModel(entry, index))
				.filter((model): model is ChatModelOption => model !== null);

			if (models.length === 0) {
				throw new Error('Model catalog response has no valid entries.');
			}

			return { models };
		},
	});

	const models = query.data?.models ?? [];
	const defaultModel = useMemo<ChatModelOption | null>(() => models[0] ?? null, [models]);

	return {
		models,
		default: defaultModel,
		isLoading: query.isLoading,
		isError: query.isError,
		hasCatalog: models.length > 0,
		error: query.error ?? null,
	};
}

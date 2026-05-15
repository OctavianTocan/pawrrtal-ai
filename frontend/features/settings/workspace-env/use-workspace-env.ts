'use client';

import { type UseMutationResult, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { useAuthedQuery } from '@/hooks/use-authed-query';
import { API_ENDPOINTS } from '@/lib/api';

/**
 * Canonical list of overridable workspace env keys, kept in sync with
 * `OVERRIDABLE_KEYS` in `backend/app/core/keys.py`. The shared string union
 * type is exposed so consumers can avoid hardcoding bare strings.
 *
 * Adding a key here requires the matching change on the backend
 * `OVERRIDABLE_KEYS` frozenset; the PUT endpoint rejects anything not in
 * its allowlist with HTTP 400.
 */
export const WORKSPACE_ENV_KEY_IDS = [
	'GEMINI_API_KEY',
	'CLAUDE_CODE_OAUTH_TOKEN',
	'EXA_API_KEY',
	'XAI_API_KEY',
	'NOTION_API_KEY',
] as const satisfies readonly string[];

/** Union of valid workspace env key names. Derived from `WORKSPACE_ENV_KEY_IDS`. */
export type WorkspaceEnvKey = (typeof WORKSPACE_ENV_KEY_IDS)[number];

/**
 * Response shape returned by `GET /api/v1/workspaces/{workspace_id}/env`
 * and `PUT /api/v1/workspaces/{workspace_id}/env`. The backend always
 * returns every key in `OVERRIDABLE_KEYS`; unset keys come back with an
 * empty-string value so the form can render every input without an extra
 * schema fetch.
 */
export interface WorkspaceEnvResponse {
	/** Map of every overridable key to its current value (empty string when unset). */
	vars: Record<WorkspaceEnvKey, string>;
}

/** Minimal workspace shape pulled from `GET /api/v1/workspaces`. */
interface WorkspaceSummary {
	id: string;
	is_default: boolean;
}

/** React Query cache key shared by the GET hook and the mutation invalidate. */
const WORKSPACE_ENV_QUERY_KEY = ['workspace-env'] as const;

/** Stale-time for the workspace list lookup that drives env-key fetches. */
const WORKSPACES_LIST_STALE_MS = 5 * 60 * 1000;

/**
 * Backend error envelope when validation fails. FastAPI's `HTTPException`
 * surfaces the message under `detail`; everything else falls through.
 */
interface BackendErrorBody {
	detail?: string;
}

/**
 * Parse a backend error message out of a thrown `useAuthedFetch` error.
 *
 * `useAuthedFetch` throws an `Error` whose message is
 * `"API Error: 422 Unprocessable Entity. Body: {\"detail\": \"...\"}"`.
 * The raw string is unfriendly in the UI, so this extracts `detail`
 * (or `message`) and falls back to the original string.
 */
export function extractApiErrorMessage(error: unknown, fallback: string): string {
	if (!(error instanceof Error)) return fallback;
	const match = error.message.match(/Body:\s*(\{.*\})\s*$/s);
	const body = match?.[1];
	if (!body) return error.message;
	try {
		const parsed = JSON.parse(body) as BackendErrorBody;
		if (typeof parsed.detail === 'string' && parsed.detail.length > 0) {
			return parsed.detail;
		}
	} catch {
		/* fall through */
	}
	return error.message;
}

/**
 * Internal helper: fetch the current user's default workspace ID.
 *
 * Mirrors the pattern in `useWorkspaceTree` — pull the workspace list,
 * prefer the row flagged `is_default`, fall back to the first entry.
 * Cached separately under the `workspaces` query key so adding/removing
 * workspaces only triggers one refetch.
 */
function useDefaultWorkspaceId(): string | null {
	const authedFetch = useAuthedFetch();
	const workspacesQuery = useQuery<WorkspaceSummary[]>({
		queryKey: ['workspaces'],
		queryFn: async (): Promise<WorkspaceSummary[]> => {
			const res = await authedFetch(API_ENDPOINTS.workspaces.list);
			return res.json() as Promise<WorkspaceSummary[]>;
		},
		staleTime: WORKSPACES_LIST_STALE_MS,
	});
	const defaultWorkspace =
		workspacesQuery.data?.find((w) => w.is_default) ?? workspacesQuery.data?.[0];
	return defaultWorkspace?.id ?? null;
}

/**
 * Read the authenticated user's default-workspace env overrides.
 *
 * Server-state read; cookie-authed; cached under
 * {@link WORKSPACE_ENV_QUERY_KEY}. The mutation hook below invalidates
 * this key on save so the UI re-fetches the canonical state from disk
 * (which reflects the empty-string strip step).
 *
 * The query is enabled only after the workspace list resolves — until
 * then it stays in the idle state so the Settings UI can render its
 * skeleton without firing a 404.
 */
export function useWorkspaceEnv(): ReturnType<typeof useAuthedQuery<WorkspaceEnvResponse>> {
	const workspaceId = useDefaultWorkspaceId();
	return useAuthedQuery<WorkspaceEnvResponse>(
		[...WORKSPACE_ENV_QUERY_KEY, workspaceId ?? ''],
		workspaceId ? API_ENDPOINTS.workspaces.env(workspaceId) : '',
		{ enabled: workspaceId !== null }
	);
}

/**
 * Persist a partial set of workspace env overrides.
 *
 * The backend `PUT` is PATCH-like: keys not present in `vars` are left
 * untouched on disk. Empty-string values clear the corresponding key
 * (the on-disk file omits empty entries), which the resolver treats as
 * "use the gateway default".
 *
 * Targets the user's default workspace. Multi-workspace switching from
 * the Settings UI is a follow-up (`pawrrtal-TBD`).
 */
export function useUpsertWorkspaceEnv(): UseMutationResult<
	WorkspaceEnvResponse,
	Error,
	Partial<Record<WorkspaceEnvKey, string>>
> {
	const fetcher = useAuthedFetch();
	const queryClient = useQueryClient();
	const workspaceId = useDefaultWorkspaceId();

	return useMutation({
		mutationKey: ['workspace-env', 'upsert', workspaceId ?? ''],
		mutationFn: async (
			vars: Partial<Record<WorkspaceEnvKey, string>>
		): Promise<WorkspaceEnvResponse> => {
			if (!workspaceId) {
				throw new Error(
					'Cannot save workspace env: default workspace has not loaded yet.'
				);
			}
			const response = await fetcher(API_ENDPOINTS.workspaces.env(workspaceId), {
				method: 'PUT',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ vars }),
			});
			return (await response.json()) as WorkspaceEnvResponse;
		},
		onSuccess: (next) => {
			queryClient.setQueryData<WorkspaceEnvResponse>(
				[...WORKSPACE_ENV_QUERY_KEY, workspaceId ?? ''],
				next
			);
		},
	});
}

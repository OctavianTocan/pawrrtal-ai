'use client';

import { type UseMutationResult, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { useAuthedQuery } from '@/hooks/use-authed-query';
import { API_ENDPOINTS } from '@/lib/api';
import type { Project } from '@/lib/types';

/** React-Query cache key for the project list. */
const PROJECTS_QUERY_KEY = ['projects'] as const;

/** Variables required to create a new project. */
interface CreateProjectVariables {
	name: string;
}

/** Variables required to rename a project. */
interface RenameProjectVariables {
	projectId: string;
	name: string;
}

/** Variables required to assign / unassign a conversation to a project. */
interface AssignConversationVariables {
	conversationId: string;
	/** Pass null to unassign and put the conversation back in the Chats list. */
	projectId: string | null;
}

/**
 * Fetch every project owned by the authenticated user. Cached under
 * `['projects']` so mutations can invalidate or optimistically update.
 */
export function useGetProjects(): ReturnType<typeof useAuthedQuery<Project[]>> {
	return useAuthedQuery<Project[]>(PROJECTS_QUERY_KEY, API_ENDPOINTS.projects.list);
}

/**
 * Create a new project. Invalidates the project list on success so the
 * sidebar re-renders with the new row.
 */
export function useCreateProject(): UseMutationResult<Project, Error, CreateProjectVariables> {
	const fetcher = useAuthedFetch();
	const queryClient = useQueryClient();

	return useMutation({
		mutationKey: ['projects', 'create'],
		mutationFn: async ({ name }: CreateProjectVariables): Promise<Project> => {
			const response = await fetcher(API_ENDPOINTS.projects.create, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ name }),
			});
			return (await response.json()) as Project;
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
		},
	});
}

/**
 * Rename a project. Optimistically updates the cached list so the new
 * name appears before the server round-trip finishes.
 */
export function useRenameProject(): UseMutationResult<Project, Error, RenameProjectVariables> {
	const fetcher = useAuthedFetch();
	const queryClient = useQueryClient();

	return useMutation({
		mutationKey: ['projects', 'rename'],
		mutationFn: async ({ projectId, name }: RenameProjectVariables): Promise<Project> => {
			const response = await fetcher(API_ENDPOINTS.projects.update(projectId), {
				method: 'PATCH',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ name }),
			});
			return (await response.json()) as Project;
		},
		onSuccess: (updated) => {
			queryClient.setQueryData<Project[] | undefined>(PROJECTS_QUERY_KEY, (current) =>
				current?.map((project) => (project.id === updated.id ? updated : project))
			);
			queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
		},
	});
}

/**
 * Assign a conversation to a project (or clear it). Sends the explicit
 * `project_id_set: true` companion flag so the backend treats `null` as
 * "remove from current project" rather than "leave alone".
 */
export function useAssignConversationToProject(): UseMutationResult<
	void,
	Error,
	AssignConversationVariables
> {
	const fetcher = useAuthedFetch();
	const queryClient = useQueryClient();

	return useMutation({
		mutationKey: ['conversations', 'assign-project'],
		mutationFn: async ({
			conversationId,
			projectId,
		}: AssignConversationVariables): Promise<void> => {
			await fetcher(`/api/v1/conversations/${conversationId}`, {
				method: 'PATCH',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					project_id: projectId,
					project_id_set: true,
				}),
			});
		},
		onSuccess: () => {
			// Invalidate both the conversations list (its rows carry
			// `project_id`, used by any future per-project view) and the
			// projects list (counts/membership shown alongside each row).
			queryClient.invalidateQueries({ queryKey: ['conversations'] });
			queryClient.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY });
		},
	});
}

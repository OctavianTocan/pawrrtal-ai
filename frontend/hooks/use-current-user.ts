'use client';

import { API_ENDPOINTS } from '@/lib/api';
import { useAuthedQuery } from './use-authed-query';

/** Cache key for the current user endpoint. */
const CURRENT_USER_QUERY_KEY = ['current-user'] as const;

/** Shape returned by FastAPI-Users' GET /users/me (UserRead). */
export interface CurrentUser {
	/** Stable UUID for the authenticated user. */
	id: string;
	/** Account email address. */
	email: string;
	/** Whether the account is active. */
	is_active: boolean;
	/** Whether the user has admin privileges. */
	is_superuser: boolean;
	/** Whether the email address has been verified. */
	is_verified: boolean;
}

/**
 * Fetch the authenticated user's account data from GET /users/me.
 *
 * Returns id, email, and account flags. For display name and role,
 * compose with `useGetPersonalization()`.
 */
export function useCurrentUser(): ReturnType<typeof useAuthedQuery<CurrentUser>> {
	return useAuthedQuery<CurrentUser>(CURRENT_USER_QUERY_KEY, API_ENDPOINTS.auth.me);
}

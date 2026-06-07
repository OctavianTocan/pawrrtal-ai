'use client';

import { useAuthedQuery } from '@/hooks/use-authed-query';
import { API_ENDPOINTS } from '@/lib/api';

const ONBOARDING_STATUS_QUERY_KEY = ['onboarding-status'] as const;

interface OnboardingStatusResponse {
	has_workspace_ready: boolean;
}

export interface OnboardingReadiness {
	/** True when the server confirms a default workspace exists for the current user. */
	hasWorkspaceReady: boolean;
	/** True while the readiness endpoint is loading. */
	isLoading: boolean;
	/** True when the readiness endpoint failed. */
	isError: boolean;
	/** True while a retry is in flight. */
	isRefetching: boolean;
	/** Retry the readiness check. */
	refetch: () => void;
}

/**
 * Unified onboarding readiness signal used by app bootstrap + chat gating.
 *
 * - `hasWorkspaceReady`: derived from `GET /api/v1/workspaces/onboarding-status`.
 */
export function useOnboardingReadiness(): OnboardingReadiness {
	const onboardingStatusQuery = useAuthedQuery<OnboardingStatusResponse>(
		ONBOARDING_STATUS_QUERY_KEY,
		API_ENDPOINTS.workspaces.onboardingStatus,
		{
			staleTime: 15 * 1000,
		}
	);

	return {
		hasWorkspaceReady: onboardingStatusQuery.data?.has_workspace_ready ?? false,
		isLoading: onboardingStatusQuery.isLoading,
		isError: onboardingStatusQuery.isError,
		isRefetching: onboardingStatusQuery.isRefetching,
		refetch: () => {
			void onboardingStatusQuery.refetch();
		},
	};
}

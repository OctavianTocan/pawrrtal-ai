'use client';

import { useEffect, useState } from 'react';
import { useAuthedQuery } from '@/hooks/use-authed-query';
import {
	API_ENDPOINTS,
	BACKEND_CONFIG_CHANGED_EVENT,
	getBackendConfigFingerprint,
	hasBackendConfig,
} from '@/lib/api';

const ONBOARDING_STATUS_QUERY_KEY = ['onboarding-status'] as const;

interface OnboardingStatusResponse {
	has_workspace_ready: boolean;
}

export interface OnboardingReadiness {
	/** Whether the user has an explicit backend target configured in this browser profile. */
	hasBackendConfig: boolean;
	/** True when the server confirms a default workspace exists for the current user. */
	hasWorkspaceReady: boolean;
	/** True while the readiness endpoint is loading with a configured backend. */
	isLoading: boolean;
	/** True when the readiness endpoint failed while a backend is configured. */
	isError: boolean;
}

function readBackendConfigState(): boolean {
	return hasBackendConfig();
}

/**
 * Unified onboarding readiness signal used by app bootstrap + chat gating.
 *
 * - `hasBackendConfig`: derived from explicit client runtime backend config.
 * - `hasWorkspaceReady`: derived from `GET /api/v1/workspaces/onboarding-status`.
 */
export function useOnboardingReadiness(): OnboardingReadiness {
	const [state, setState] = useState(() => ({
		hasBackend: readBackendConfigState(),
		backendFingerprint: getBackendConfigFingerprint(),
	}));
	const { hasBackend, backendFingerprint } = state;
	const onboardingStatusQuery = useAuthedQuery<OnboardingStatusResponse>(
		[...ONBOARDING_STATUS_QUERY_KEY, backendFingerprint],
		API_ENDPOINTS.workspaces.onboardingStatus,
		{
			enabled: hasBackend,
			staleTime: 15 * 1000,
		}
	);

	useEffect(() => {
		const sync = (): void => {
			const nextHasBackend = readBackendConfigState();
			const nextBackendFingerprint = getBackendConfigFingerprint();
			setState((current) => {
				if (
					current.hasBackend === nextHasBackend &&
					current.backendFingerprint === nextBackendFingerprint
				) {
					return current;
				}
				return {
					hasBackend: nextHasBackend,
					backendFingerprint: nextBackendFingerprint,
				};
			});
		};
		sync();

		if (typeof window === 'undefined') return;

		window.addEventListener('storage', sync);
		window.addEventListener(BACKEND_CONFIG_CHANGED_EVENT, sync);

		return () => {
			window.removeEventListener('storage', sync);
			window.removeEventListener(BACKEND_CONFIG_CHANGED_EVENT, sync);
		};
	}, []);

	return {
		hasBackendConfig: hasBackend,
		hasWorkspaceReady: hasBackend
			? (onboardingStatusQuery.data?.has_workspace_ready ?? false)
			: false,
		isLoading: hasBackend ? onboardingStatusQuery.isLoading : false,
		isError: hasBackend ? onboardingStatusQuery.isError : false,
	};
}

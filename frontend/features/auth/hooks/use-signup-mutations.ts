import { useMutation, useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS, apiFetch } from '@/lib/api';

/** Arguments for a standard email/password signup request. */
export interface SignupArgs {
	email: string;
	password: string;
}

/** Error structure from FastAPI. */
interface FastAPIError {
	detail: string | Array<unknown>;
}

/** Helper to parse standard FastAPI error responses or throw generic fallbacks. */
async function handleResponseError(response: Response, defaultMessage: string): Promise<never> {
	let message = defaultMessage;
	try {
		const errorBody = (await response.json()) as FastAPIError;
		if (typeof errorBody?.detail === 'string') {
			message = errorBody.detail;
		} else if (Array.isArray(errorBody?.detail)) {
			message = 'Invalid request payload.';
		}
	} catch {
		// If JSON parsing fails, we keep the default message.
	}
	throw new Error(message);
}

/**
 * Hook to authenticate via standard email/password form data.
 */
export function useSignupMutation() {
	const queryClient = useQueryClient();

	return useMutation<void, Error, SignupArgs>({
		mutationFn: async ({ email, password }) => {
			const response = await apiFetch(API_ENDPOINTS.auth.register, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({ email, password }),
			});

			if (!response.ok) {
				await handleResponseError(response, 'Unable to sign up with those credentials.');
			}

			// We need to log the user in after we've created the account.
			// Otherwise, it'll feel odd to still need to log in after signing up.
			const loginResponse = await apiFetch(API_ENDPOINTS.auth.login, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
				},
				body: new URLSearchParams({
					username: email,
					password: password,
				}),
				credentials: 'include',
			});

			if (!loginResponse.ok) {
				await handleResponseError(loginResponse, 'Unable to log in after sign up.');
			}
		},
		onSuccess: () => {
			// Invalidate any queries that depend on auth state (e.g. user profile).
			void queryClient.invalidateQueries();
		},
	});
}

'use client';

import type React from 'react';
import { useId, useState } from 'react';
import { useDevAdminLoginMutation, useLoginMutation } from './hooks/use-login-mutations';
import { LoginFormView } from './LoginFormView';

interface LoginFormProps extends React.ComponentProps<'div'> {
	canUseDevAdminLogin?: boolean;
	/**
	 * Path to navigate to after a successful sign-in.
	 *
	 * The login page reads the URL's ``?redirect=`` query server-side
	 * (Next.js 15+ ``searchParams`` is a Promise) and validates it
	 * before threading the value here. Defaults to ``/``.
	 *
	 * Keeping the read on the server keeps this component prerender-
	 * safe — using ``useSearchParams`` inside would force a CSR bail-
	 * out for the entire ``/login`` page.
	 */
	postLoginTarget?: string;
}

/**
 * Container for the login form.
 *
 * Owns form state, validation, API calls, and navigation on success.
 * Delegates all rendering to `LoginFormView`.
 *
 * @param canUseDevAdminLogin - Whether to show the dev-only admin shortcut button.
 * @param postLoginTarget - Validated path to load after sign-in.
 */
export function LoginForm({
	className,
	canUseDevAdminLogin = false,
	postLoginTarget = '/',
	...props
}: LoginFormProps): React.JSX.Element {
	// Destructure onSubmit from rest to avoid conflict with our custom onSubmit prop.
	const { onSubmit: _nativeOnSubmit, ...divProps } = props;
	const formId = useId();
	const emailId = `${formId}-email`;
	const passwordId = `${formId}-password`;

	const [email, setEmail] = useState('');
	const [password, setPassword] = useState('');
	const [localErrorMessage, setLocalErrorMessage] = useState('');

	const loginMutation = useLoginMutation();
	const devLoginMutation = useDevAdminLoginMutation();

	const isLoading = loginMutation.isPending || devLoginMutation.isPending;

	/**
	 * Maps browser-specific fetch failures to a clearer backend-unreachable message,
	 * while preserving any other surfaced error text.
	 */
	const setFriendlyNetworkError = (error: unknown): void => {
		if (!(error instanceof Error)) {
			return;
		}

		const normalizedMessage = error.message.toLowerCase();
		if (error instanceof TypeError && normalizedMessage.includes('fetch')) {
			setLocalErrorMessage('Unable to connect to the backend. Is the server running?');
			return;
		}

		if (error.message) {
			setLocalErrorMessage(error.message);
		}
	};

	// Prefer the local (network) error if the service failed to be reached entirely,
	// otherwise show the specific API error from React Query.
	const currentError =
		localErrorMessage || loginMutation.error?.message || devLoginMutation.error?.message || '';

	/** Form submit handler — prevents default page refresh. */
	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
		event.preventDefault();
		setLocalErrorMessage('');
		loginMutation.reset();
		devLoginMutation.reset();

		try {
			await loginMutation.mutateAsync({ email, password });
			window.location.replace(postLoginTarget);
		} catch (error) {
			setFriendlyNetworkError(error);
		}
	};

	/** Calls a backend-only shortcut that logs in with the seeded admin account. */
	const handleDevAdminLogin = async (): Promise<void> => {
		setLocalErrorMessage('');
		loginMutation.reset();
		devLoginMutation.reset();

		try {
			await devLoginMutation.mutateAsync();
			window.location.replace(postLoginTarget);
		} catch (error) {
			setFriendlyNetworkError(error);
		}
	};

	return (
		<LoginFormView
			className={className}
			emailId={emailId}
			passwordId={passwordId}
			email={email}
			onEmailChange={setEmail}
			password={password}
			onPasswordChange={setPassword}
			errorMessage={currentError}
			isLoading={isLoading}
			canUseDevAdminLogin={canUseDevAdminLogin}
			onSubmit={handleSubmit}
			onDevAdminLogin={handleDevAdminLogin}
			{...divProps}
		/>
	);
}

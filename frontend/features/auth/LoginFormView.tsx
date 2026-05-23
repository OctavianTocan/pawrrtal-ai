import { Loader2Icon } from 'lucide-react';
import Link from 'next/link';
import type React from 'react';
import { AppleIcon } from '@/components/brand-icons/AppleIcon';
import { GoogleIcon } from '@/components/brand-icons/GoogleIcon';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { API_BASE_URL } from '@/lib/api';
import { cn } from '@/lib/utils';

/** Backend OAuth start URLs the SSO buttons navigate to. */
const OAUTH_START_URLS = {
	google: `${API_BASE_URL}/api/v1/auth/oauth/google/start`,
	apple: `${API_BASE_URL}/api/v1/auth/oauth/apple/start`,
} as const;

export interface LoginFormViewProps extends Omit<React.ComponentProps<'div'>, 'onSubmit'> {
	/** Unique ID prefix for form field elements. */
	emailId: string;
	/** Unique ID prefix for the password field. */
	passwordId: string;
	/** Current email input value. */
	email: string;
	/** Called on every email keystroke. */
	onEmailChange: (value: string) => void;
	/** Current password input value. */
	password: string;
	/** Called on every password keystroke. */
	onPasswordChange: (value: string) => void;
	/** Error message to display, or empty string for none. */
	errorMessage: string;
	/** Whether a login request is in-flight (disables buttons). */
	isLoading: boolean;
	/** Whether the dev-only admin shortcut is available. */
	canUseDevAdminLogin: boolean;
	/** Called when the form is submitted. */
	onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
	/** Called when the "Dev Admin" button is clicked. */
	onDevAdminLogin: () => void;
}

/**
 * Pure presentation layer for the login form.
 *
 * Renders the card with email/password fields, error alert, submit button,
 * optional dev-admin shortcut, and signup link. All state and async logic
 * live in the container (`LoginForm`).
 */
export function LoginFormView({
	className,
	emailId,
	passwordId,
	email,
	onEmailChange,
	password,
	onPasswordChange,
	errorMessage,
	isLoading,
	canUseDevAdminLogin,
	onSubmit,
	onDevAdminLogin,
	...props
}: LoginFormViewProps): React.JSX.Element {
	return (
		<div className={cn('flex flex-col gap-6', className)} {...props}>
			<Card>
				<CardHeader>
					<CardTitle>Login to your account</CardTitle>
					<CardDescription>
						Enter your email below to login to your account
					</CardDescription>
				</CardHeader>
				<CardContent>
					<form onSubmit={onSubmit}>
						<FieldGroup>
							{/* -- Alert -- */}
							{errorMessage && (
								<Alert variant="destructive">
									<AlertTitle>Error</AlertTitle>
									<AlertDescription>{errorMessage}</AlertDescription>
								</Alert>
							)}
							{/* -- Email -- */}
							<Field>
								<FieldLabel htmlFor={emailId}>Email</FieldLabel>
								<Input
									id={emailId}
									type="email"
									placeholder="m@example.com"
									autoComplete="email"
									required
									value={email}
									onChange={(e) => onEmailChange(e.target.value)}
								/>
							</Field>
							{/* -- Password -- */}
							<Field>
								<div className="flex items-center">
									<FieldLabel htmlFor={passwordId}>Password</FieldLabel>
									<Link
										href="/forgot-password"
										className="ml-auto inline-block text-sm underline-offset-4 hover:underline"
									>
										Forgot your password?
									</Link>
								</div>
								<Input
									id={passwordId}
									type="password"
									autoComplete="current-password"
									required
									value={password}
									onChange={(e) => onPasswordChange(e.target.value)}
								/>
							</Field>
							{/* -- Actions -- */}
							<Field>
								<Button
									className="cursor-pointer"
									type="submit"
									disabled={isLoading}
								>
									{isLoading && (
										<Loader2Icon
											className="mr-2 size-4 animate-spin"
											aria-hidden="true"
										/>
									)}
									{isLoading ? 'Logging in...' : 'Login'}
								</Button>
								{canUseDevAdminLogin && (
									<>
										<Button
											className="cursor-pointer"
											variant="outline"
											type="button"
											onClick={onDevAdminLogin}
											disabled={isLoading}
										>
											Dev Admin
										</Button>
										<FieldDescription className="text-center text-sm">
											Dev-only shortcut for the seeded admin account.
										</FieldDescription>
									</>
								)}
								{/*
								 * SSO buttons navigate to backend start endpoints. The
								 * backend redirects to Google/Apple consent (when env
								 * vars are configured) or returns 503 with a clear
								 * "not configured" message otherwise — see
								 * backend/app/api/oauth.py.
								 */}
								<Button
									className="cursor-pointer gap-2"
									disabled={isLoading}
									onClick={() => {
										window.location.href = OAUTH_START_URLS.google;
									}}
									type="button"
									variant="outline"
								>
									<GoogleIcon className="size-4" />
									Continue with Google
								</Button>
								<Button
									className="cursor-pointer gap-2"
									disabled={isLoading}
									onClick={() => {
										window.location.href = OAUTH_START_URLS.apple;
									}}
									type="button"
									variant="outline"
								>
									<AppleIcon className="size-4" />
									Continue with Apple
								</Button>
								<FieldDescription className="text-center">
									Don&apos;t have an account? <Link href="/signup">Sign up</Link>
								</FieldDescription>
							</Field>
						</FieldGroup>
					</form>
				</CardContent>
			</Card>
		</div>
	);
}

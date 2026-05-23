/**
 * Self-service registration card: posts to FastAPI then performs an automatic login.
 *
 * @fileoverview Uses `credentials: 'include'` on follow-up login so the session cookie is stored for the SPA.
 */

'use client';

import { Loader2Icon } from 'lucide-react';
import Link from 'next/link';
import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { API_ENDPOINTS, apiFetch } from '@/lib/api';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';

/** Self-service registration form. */
export function SignupForm({ ...props }: React.ComponentProps<typeof Card>) {
	const [errorMessage, setErrorMessage] = useState('');
	// To disable buttons while submitting.
	const [submissionStatus, setSubmissionStatus] = useState<'idle' | 'submitting'>('idle');
	// SSR-stable unique IDs so each Field's label and input pair correctly even
	// if the form is rendered more than once on the same page.
	const nameId = useId();
	const emailId = useId();
	const passwordId = useId();
	const confirmPasswordId = useId();
	const isSubmitting = submissionStatus === 'submitting';

	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
		// Stops the page from refreshing.
		event.preventDefault();

		// Disable the button while submitting.
		setSubmissionStatus('submitting');

		const formData = new FormData(event.target as HTMLFormElement);
		const email = formData.get('email')?.toString() ?? '';
		const password = formData.get('password')?.toString() ?? '';
		const confirmPassword = formData.get('confirm-password')?.toString() ?? '';
		if (password !== confirmPassword) {
			setErrorMessage('Passwords do not match');
			// Enable the button again.
			setSubmissionStatus('idle');
			return;
		}

		// TODO: This inline fetch needs to be moved to a custom hook.
		const response = await apiFetch(API_ENDPOINTS.auth.register, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				email: email,
				password: password,
			}),
		});

		// TODO: Check detail for error. ({"detail":"REGISTER_USER_ALREADY_EXISTS"}
		// TODO: Check response for success: ({
		//     "id": "73946aca-98f2-45e8-8690-4da5b62cffbd",
		//     "email": "tocanoctavian@gmail.com",
		//     "is_active": true,
		//     "is_superuser": false,
		//     "is_verified": false
		// }))
		// TODO: If success, redirect back to where the user came from, but with a success message.
		if (!response.ok) {
			const error = await response.json();
			setErrorMessage(error.detail);
			// Enable the button again.
			setSubmissionStatus('idle');
			return;
		}

		// Reset the error message.
		// We do it here, so the Alert component doesn't jump unnecessarily every time we press the submit button.
		setErrorMessage('');

		// Auto-login so the user doesn't need to sign in again after registering.
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
			setErrorMessage('Account created but sign-in failed. Please log in manually.');
			setSubmissionStatus('idle');
			return;
		}

		// Full-page navigation ensures the session cookie is committed before
		// any authed queries fire. Client-side routing races cookie propagation.
		window.location.replace('/');
	};

	return (
		<Card {...props}>
			<CardHeader>
				<CardTitle>Create an account</CardTitle>
				<CardDescription>
					Enter your information below to create your account
				</CardDescription>
			</CardHeader>
			<CardContent>
				<form onSubmit={handleSubmit}>
					<FieldGroup>
						{/* -- Alert -- */}
						{errorMessage && (
							<Alert variant="destructive">
								<AlertTitle>Error</AlertTitle>
								<AlertDescription>{errorMessage}</AlertDescription>
							</Alert>
						)}
						<Field>
							<FieldLabel htmlFor={nameId}>Full Name</FieldLabel>
							<Input
								id={nameId}
								type="text"
								placeholder="John Doe"
								required
								name="name"
							/>
						</Field>
						<Field>
							<FieldLabel htmlFor={emailId}>Email</FieldLabel>
							<Input
								id={emailId}
								type="email"
								placeholder="m@example.com"
								required
								name="email"
							/>
							<FieldDescription>
								We&apos;ll use this to contact you. We will not share your email
								with anyone else.
							</FieldDescription>
						</Field>
						<Field>
							<FieldLabel htmlFor={passwordId}>Password</FieldLabel>
							<Input id={passwordId} type="password" required name="password" />
							{/* TODO: We're not validating the password strength here. */}
							<FieldDescription>Must be at least 8 characters long.</FieldDescription>
						</Field>
						<Field>
							<FieldLabel htmlFor={confirmPasswordId}>Confirm Password</FieldLabel>
							<Input
								id={confirmPasswordId}
								type="password"
								required
								name="confirm-password"
							/>
							<FieldDescription>Please confirm your password.</FieldDescription>
						</Field>
						<FieldGroup>
							<Field>
								<Button type="submit" disabled={isSubmitting}>
									{isSubmitting && (
										<Loader2Icon
											className="mr-2 size-4 animate-spin"
											aria-hidden="true"
										/>
									)}
									{isSubmitting ? 'Creating Account...' : 'Create Account'}
								</Button>
								{/* <Button variant="outline" type="button">
                                    Sign up with Google
                                </Button> */}
								<FieldDescription className="px-6 text-center">
									Already have an account? <Link href="/login">Sign in</Link>
								</FieldDescription>
							</Field>
						</FieldGroup>
					</FieldGroup>
				</form>
			</CardContent>
		</Card>
	);
}

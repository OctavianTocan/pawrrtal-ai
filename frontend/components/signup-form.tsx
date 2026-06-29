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
import { useSignupMutation } from '@/features/auth/hooks/use-signup-mutations';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';

/** Self-service registration form. */
export function SignupForm({ ...props }: React.ComponentProps<typeof Card>) {
  const [errorMessage, setErrorMessage] = useState('');
  const signupMutation = useSignupMutation();
  const isSubmitting = signupMutation.isPending;

  // SSR-stable unique IDs so each Field's label and input pair correctly even
  // if the form is rendered more than once on the same page.
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();
  const confirmPasswordId = useId();

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    // Stops the page from refreshing.
    event.preventDefault();

    const formData = new FormData(event.target as HTMLFormElement);
    const email = formData.get('email')?.toString() ?? '';
    const password = formData.get('password')?.toString() ?? '';
    const confirmPassword = formData.get('confirm-password')?.toString() ?? '';
    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match');
      return;
    }

    setErrorMessage('');
    signupMutation.mutate(
      { email, password },
      {
        onSuccess: () => {
          // Full-page navigation ensures the session cookie is committed before
          // any authed queries fire. Client-side routing races cookie propagation.
          window.location.replace('/');
        },
        onError: (error) => {
          setErrorMessage(error.message);
        },
      }
    );
  };

  return (
    <Card {...props}>
      <CardHeader>
        <CardTitle>Create an account</CardTitle>
        <CardDescription>Enter your information below to create your account</CardDescription>
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
              <Input id={nameId} name="name" placeholder="John Doe" required type="text" />
            </Field>
            <Field>
              <FieldLabel htmlFor={emailId}>Email</FieldLabel>
              <Input id={emailId} name="email" placeholder="m@example.com" required type="email" />
              <FieldDescription>
                We&apos;ll use this to contact you. We will not share your email with anyone else.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor={passwordId}>Password</FieldLabel>
              <Input id={passwordId} name="password" required type="password" />
              {/* TODO: We're not validating the password strength here. */}
              <FieldDescription>Must be at least 8 characters long.</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor={confirmPasswordId}>Confirm Password</FieldLabel>
              <Input id={confirmPasswordId} name="confirm-password" required type="password" />
              <FieldDescription>Please confirm your password.</FieldDescription>
            </Field>
            <FieldGroup>
              <Field>
                <Button disabled={isSubmitting} type="submit">
                  {isSubmitting && <Loader2Icon aria-hidden="true" className="mr-2 size-4 animate-spin" />}
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

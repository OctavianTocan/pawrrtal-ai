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
import { API_ENDPOINTS, getBrowserApiUrl } from '@/lib/api';
import { cn } from '@/lib/utils';

/** Backend OAuth start URLs the SSO buttons navigate to. */
const OAUTH_START_URLS = {
  google: '/api/v1/auth/oauth/google/start',
  apple: '/api/v1/auth/oauth/apple/start',
} as const;

type OAuthProvider = keyof typeof OAUTH_START_URLS;

interface SsoButtonProps {
  disabled: boolean;
  icon: React.ReactNode;
  label: string;
  provider: OAuthProvider;
}

function SsoButton({ disabled, icon, label, provider }: SsoButtonProps): React.JSX.Element {
  return (
    <Button
      className="cursor-pointer gap-2"
      disabled={disabled}
      onClick={() => {
        window.location.href = getBrowserApiUrl(OAUTH_START_URLS[provider]);
      }}
      type="button"
      variant="outline"
    >
      {icon}
      {label}
    </Button>
  );
}

function buildDevLoginFormAction(postLoginTarget: string): string {
  const base = getBrowserApiUrl(API_ENDPOINTS.auth.devLoginBrowser);
  return `${base}?redirect_to=${encodeURIComponent(postLoginTarget)}`;
}

export interface DevAdminLoginHandlers {
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
  onTouchEnd: (event: React.TouchEvent<HTMLButtonElement>) => void;
}

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
  /** ID of the browser fallback form submitted before hydration. */
  devAdminFormId: string;
  /** Hydrated button handlers for the dev-admin shortcut. */
  devAdminLoginHandlers: DevAdminLoginHandlers;
  /** Safe relative path to load after a successful login. */
  postLoginTarget: string;
  /** Called when the form is submitted. */
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
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
  devAdminFormId,
  devAdminLoginHandlers,
  postLoginTarget,
  onSubmit,
  ...props
}: LoginFormViewProps): React.JSX.Element {
  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card>
        <CardHeader>
          <CardTitle>Login to your account</CardTitle>
          <CardDescription>Enter your email below to login to your account</CardDescription>
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
              <Field>
                <FieldLabel htmlFor={emailId}>Email</FieldLabel>
                <Input
                  autoComplete="email"
                  id={emailId}
                  onChange={(e) => onEmailChange(e.target.value)}
                  placeholder="m@example.com"
                  required
                  type="email"
                  value={email}
                />
              </Field>
              <Field>
                <div className="flex items-center">
                  <FieldLabel htmlFor={passwordId}>Password</FieldLabel>
                  <Link
                    className="ml-auto inline-block text-sm underline-offset-4 hover:underline"
                    href="/forgot-password"
                  >
                    Forgot your password?
                  </Link>
                </div>
                <Input
                  autoComplete="current-password"
                  id={passwordId}
                  onChange={(e) => onPasswordChange(e.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </Field>
              <Field>
                <Button className="cursor-pointer" disabled={isLoading} type="submit">
                  {isLoading && <Loader2Icon aria-hidden="true" className="mr-2 size-4 animate-spin" />}
                  {isLoading ? 'Logging in...' : 'Login'}
                </Button>
                {canUseDevAdminLogin && (
                  <>
                    <Button
                      className="cursor-pointer"
                      disabled={isLoading}
                      form={devAdminFormId}
                      onClick={devAdminLoginHandlers.onClick}
                      onTouchEnd={devAdminLoginHandlers.onTouchEnd}
                      type="submit"
                      variant="outline"
                    >
                      Dev Admin
                    </Button>
                    <FieldDescription className="text-center text-sm">
                      Dev-only shortcut for the seeded admin account.
                    </FieldDescription>
                  </>
                )}
                <SsoButton
                  disabled={isLoading}
                  icon={<GoogleIcon className="size-4" />}
                  label="Continue with Google"
                  provider="google"
                />
                <SsoButton
                  disabled={isLoading}
                  icon={<AppleIcon className="size-4" />}
                  label="Continue with Apple"
                  provider="apple"
                />
                <FieldDescription className="text-center">
                  Don&apos;t have an account? <Link href="/signup">Sign up</Link>
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
          {canUseDevAdminLogin && (
            <form action={buildDevLoginFormAction(postLoginTarget)} id={devAdminFormId} method="post">
              <input name="redirect_to" type="hidden" value={postLoginTarget} />
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

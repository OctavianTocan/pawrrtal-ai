'use client';

import type React from 'react';
import { useCallback, useId, useRef, useState } from 'react';
import { useDevAdminLoginMutation, useLoginMutation } from './hooks/use-login-mutations';
import { type DevAdminLoginHandlers, LoginFormView } from './LoginFormView';

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

function useTouchTapCommit(commit: () => void | Promise<void>): DevAdminLoginHandlers {
  const touchCommittedRef = useRef(false);

  const handleTouchEnd = useCallback(
    (event: React.TouchEvent<HTMLButtonElement>): void => {
      event.preventDefault();
      touchCommittedRef.current = true;
      void commit();
    },
    [commit]
  );

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>): void => {
      event.preventDefault();
      if (touchCommittedRef.current) {
        touchCommittedRef.current = false;
        return;
      }
      void commit();
    },
    [commit]
  );

  return {
    onClick: handleClick,
    onTouchEnd: handleTouchEnd,
  };
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
  const { onSubmit: _nativeOnSubmit, ...divProps } = props;
  const formId = useId();
  const emailId = `${formId}-email`;
  const passwordId = `${formId}-password`;
  const devAdminFormId = `${formId}-dev-admin`;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localErrorMessage, setLocalErrorMessage] = useState('');

  const loginMutation = useLoginMutation();
  const devLoginMutation = useDevAdminLoginMutation();

  const isLoading = loginMutation.isPending || devLoginMutation.isPending;

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

  const currentError = localErrorMessage || loginMutation.error?.message || devLoginMutation.error?.message || '';

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
  const devAdminLoginHandlers = useTouchTapCommit(handleDevAdminLogin);

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
      devAdminFormId={devAdminFormId}
      devAdminLoginHandlers={devAdminLoginHandlers}
      postLoginTarget={postLoginTarget}
      onSubmit={handleSubmit}
      {...divProps}
    />
  );
}

import { fireEvent, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { DevAdminLoginHandlers } from './LoginFormView';
import { LoginFormView } from './LoginFormView';

function makeDevAdminHandlers(onCommit = vi.fn()): DevAdminLoginHandlers {
  return {
    onClick: (event: React.MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      onCommit();
    },
    onTouchEnd: (event: React.TouchEvent<HTMLButtonElement>) => {
      event.preventDefault();
      onCommit();
    },
  };
}

const baseProps = {
  emailId: 'email',
  passwordId: 'password',
  email: '',
  password: '',
  errorMessage: '',
  isLoading: false,
  canUseDevAdminLogin: false,
  devAdminFormId: 'dev-admin-form',
  devAdminLoginHandlers: makeDevAdminHandlers(),
  postLoginTarget: '/',
  onEmailChange: () => undefined,
  onPasswordChange: () => undefined,
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => e.preventDefault(),
};

describe('LoginFormView', () => {
  it('renders the email + password fields and the login button', () => {
    const { getByLabelText, getByRole } = render(<LoginFormView {...baseProps} />);
    expect(getByLabelText('Email')).toBeTruthy();
    expect(getByLabelText('Password')).toBeTruthy();
    expect(getByRole('button', { name: 'Login' })).toBeTruthy();
  });

  it('renders the error alert when errorMessage is non-empty', () => {
    const { getByText } = render(<LoginFormView {...baseProps} errorMessage="Wrong password" />);
    expect(getByText('Wrong password')).toBeTruthy();
  });

  it('hides the dev-admin button when canUseDevAdminLogin is false', () => {
    const { queryByRole } = render(<LoginFormView {...baseProps} />);
    expect(queryByRole('button', { name: 'Dev Admin' })).toBeNull();
  });

  it('shows the dev-admin button when allowed and fires onDevAdminLogin', async () => {
    const onDevAdminLogin = vi.fn();
    const user = userEvent.setup();
    const { getByRole } = render(
      <LoginFormView {...baseProps} canUseDevAdminLogin devAdminLoginHandlers={makeDevAdminHandlers(onDevAdminLogin)} />
    );
    await user.click(getByRole('button', { name: 'Dev Admin' }));
    expect(onDevAdminLogin).toHaveBeenCalled();
  });

  it('wires the dev-admin touch handler for touch-style taps', () => {
    const onDevAdminLogin = vi.fn();
    const { getByRole } = render(
      <LoginFormView {...baseProps} canUseDevAdminLogin devAdminLoginHandlers={makeDevAdminHandlers(onDevAdminLogin)} />
    );
    fireEvent.touchEnd(getByRole('button', { name: 'Dev Admin' }));
    expect(onDevAdminLogin).toHaveBeenCalledTimes(1);
  });

  it('renders a form fallback for dev-admin login before hydration', () => {
    const { container, getByRole } = render(
      <LoginFormView {...baseProps} canUseDevAdminLogin postLoginTarget="/settings" />
    );
    const button = getByRole('button', { name: 'Dev Admin' });
    const fallbackForm = container.querySelector('form[action="/auth/dev-login/browser?redirect_to=%2Fsettings"]');
    expect(fallbackForm).toBeTruthy();
    expect(fallbackForm?.getAttribute('method')).toBe('post');
    expect(button.getAttribute('type')).toBe('submit');
    expect(button.getAttribute('form')).toBe(fallbackForm?.id);
    expect(fallbackForm?.querySelector('input[name="redirect_to"]')?.getAttribute('value')).toBe('/settings');
  });

  it('disables submit button when isLoading is true', () => {
    const { getByRole } = render(<LoginFormView {...baseProps} isLoading />);
    expect((getByRole('button', { name: /logging in/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('fires onEmailChange/onPasswordChange when fields are typed into', async () => {
    const onEmailChange = vi.fn();
    const onPasswordChange = vi.fn();
    const user = userEvent.setup();
    const { getByLabelText } = render(
      <LoginFormView {...baseProps} onEmailChange={onEmailChange} onPasswordChange={onPasswordChange} />
    );
    // LoginFormView is uncontrolled at the view level — each keystroke
    // emits its own onChange.  Use paste() to fire one full-string
    // change per field instead of per-character events.
    await user.click(getByLabelText('Email'));
    await user.paste('me@x.com');
    await user.click(getByLabelText('Password'));
    await user.paste('secret');
    expect(onEmailChange).toHaveBeenCalledWith('me@x.com');
    expect(onPasswordChange).toHaveBeenCalledWith('secret');
  });
});

import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LoginFormView } from './LoginFormView';

const baseProps = {
	emailId: 'email',
	passwordId: 'password',
	email: '',
	password: '',
	errorMessage: '',
	isLoading: false,
	canUseDevAdminLogin: false,
	onEmailChange: () => undefined,
	onPasswordChange: () => undefined,
	onSubmit: (e: React.FormEvent<HTMLFormElement>) => e.preventDefault(),
	onDevAdminLogin: () => undefined,
};

describe('LoginFormView', () => {
	it('renders the email + password fields and the login button', () => {
		const { getByLabelText, getByRole } = render(<LoginFormView {...baseProps} />);
		expect(getByLabelText('Email')).toBeTruthy();
		expect(getByLabelText('Password')).toBeTruthy();
		expect(getByRole('button', { name: 'Login' })).toBeTruthy();
	});

	it('renders the error alert when errorMessage is non-empty', () => {
		const { getByText } = render(
			<LoginFormView {...baseProps} errorMessage="Wrong password" />
		);
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
			<LoginFormView {...baseProps} canUseDevAdminLogin onDevAdminLogin={onDevAdminLogin} />
		);
		await user.click(getByRole('button', { name: 'Dev Admin' }));
		expect(onDevAdminLogin).toHaveBeenCalled();
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
			<LoginFormView
				{...baseProps}
				onEmailChange={onEmailChange}
				onPasswordChange={onPasswordChange}
			/>
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

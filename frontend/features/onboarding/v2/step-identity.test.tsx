import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { StepIdentity } from './step-identity';

describe('StepIdentity', () => {
	it('renders prefilled values from the profile prop', () => {
		const { getByDisplayValue } = render(
			<StepIdentity
				onContinue={vi.fn()}
				onPatch={vi.fn()}
				profile={{
					name: 'Tavi',
					companyWebsite: 'https://pawrrtal.dev',
					linkedin: '',
					role: 'Engineering',
					goals: [],
				}}
			/>
		);
		expect(getByDisplayValue('Tavi')).toBeTruthy();
		expect(getByDisplayValue('Engineering')).toBeTruthy();
		expect(getByDisplayValue('https://pawrrtal.dev')).toBeTruthy();
	});

	it('patches the profile when typing into the name field', async () => {
		const onPatch = vi.fn();
		const user = userEvent.setup();
		const { getByPlaceholderText } = render(
			<StepIdentity onContinue={vi.fn()} onPatch={onPatch} profile={{}} />
		);
		const nameInput = getByPlaceholderText('Your name');
		await user.click(nameInput);
		await user.paste('Octavian');
		expect(onPatch).toHaveBeenCalledWith({ name: 'Octavian' });
	});

	it('toggles a goal chip on click and emits the new goals array', async () => {
		const onPatch = vi.fn();
		const user = userEvent.setup();
		const { getByText } = render(
			<StepIdentity onContinue={vi.fn()} onPatch={onPatch} profile={{ goals: [] }} />
		);
		await user.click(getByText('SEO / AEO'));
		expect(onPatch).toHaveBeenCalledWith({ goals: ['SEO / AEO'] });
	});

	it('un-toggles a goal already in the goals array', async () => {
		const onPatch = vi.fn();
		const user = userEvent.setup();
		const { getByText } = render(
			<StepIdentity onContinue={vi.fn()} onPatch={onPatch} profile={{ goals: ['Writing'] }} />
		);
		await user.click(getByText('Writing'));
		expect(onPatch).toHaveBeenCalledWith({ goals: [] });
	});

	it('fires onContinue when the footer button is clicked', async () => {
		const onContinue = vi.fn();
		const user = userEvent.setup();
		const { getByRole } = render(
			<StepIdentity onContinue={onContinue} onPatch={vi.fn()} profile={{}} />
		);
		await user.click(getByRole('button', { name: /Continue/ }));
		expect(onContinue).toHaveBeenCalled();
	});
});

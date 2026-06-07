import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Dialog } from '@/components/ui/dialog';
import { OnboardingCreateWorkspaceStep } from './onboarding-create-workspace-step';

const wrap = (node: React.ReactElement): React.ReactElement => (
	<Dialog open onOpenChange={() => undefined}>
		{node}
	</Dialog>
);

describe('OnboardingCreateWorkspaceStep', () => {
	it('renders the workspace selection options', () => {
		const { container } = render(
			wrap(<OnboardingCreateWorkspaceStep onPickLocal={() => undefined} />)
		);
		expect(container.textContent).toContain('Open folder');
		expect(container.textContent).toContain('Create new');
		expect(container.textContent).not.toContain('Connect to remote server');
	});

	it('disables only the upcoming Create new option, leaving Open folder enabled', () => {
		const { container, getByText } = render(
			wrap(<OnboardingCreateWorkspaceStep onPickLocal={() => undefined} />)
		);
		const buttons = Array.from(container.querySelectorAll('button'));
		const enabled = buttons.filter((b) => !(b as HTMLButtonElement).disabled);
		expect(enabled.length).toBe(1);
		const createNew = getByText('Create new').closest('button');
		expect((createNew as HTMLButtonElement).disabled).toBe(true);
	});

	it('fires onPickLocal when the enabled "Open folder" button is clicked', async () => {
		const onPickLocal = vi.fn();
		const user = userEvent.setup();
		const { getByText } = render(
			wrap(<OnboardingCreateWorkspaceStep onPickLocal={onPickLocal} />)
		);
		await user.click(getByText('Open folder'));
		expect(onPickLocal).toHaveBeenCalled();
	});
});

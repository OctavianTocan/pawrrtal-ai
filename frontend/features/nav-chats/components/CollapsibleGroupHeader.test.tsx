import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CollapsibleGroupHeader } from './CollapsibleGroupHeader';

describe('CollapsibleGroupHeader', () => {
	it('renders the label and an item count when collapsed', () => {
		const { container } = render(
			<CollapsibleGroupHeader
				label="Today"
				isCollapsed
				itemCount={4}
				onToggle={() => undefined}
			/>
		);
		expect(container.textContent).toContain('Today');
		expect(container.textContent).toContain('4');
	});

	it('hides the count when expanded', () => {
		const { container } = render(
			<CollapsibleGroupHeader
				label="Yesterday"
				isCollapsed={false}
				itemCount={4}
				onToggle={() => undefined}
			/>
		);
		// Expanded — only the label, no '·' separator
		expect(container.textContent?.includes('·')).toBe(false);
	});

	it('fires onToggle when clicked', async () => {
		const onToggle = vi.fn();
		const user = userEvent.setup();
		const { getByRole } = render(
			<CollapsibleGroupHeader label="Today" isCollapsed itemCount={3} onToggle={onToggle} />
		);
		await user.click(getByRole('button'));
		expect(onToggle).toHaveBeenCalled();
	});
});

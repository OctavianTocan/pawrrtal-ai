import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { IntegrationsSection } from './IntegrationsSection';

describe('IntegrationsSection', () => {
	it('renders the Integrations page heading, the prototype notice, and the empty state', () => {
		const { getByRole, getByText } = render(<IntegrationsSection />);
		expect(getByRole('heading', { name: 'Integrations' })).toBeTruthy();
		expect(getByText('Your integrations')).toBeTruthy();
		expect(getByText('Coming soon')).toBeTruthy();
		expect(getByText('No integrations connected yet.')).toBeTruthy();
	});

	it('opens the Add Integration modal when the trigger button is clicked', async () => {
		const user = userEvent.setup();
		const { getByRole, queryByText, getByPlaceholderText } = render(<IntegrationsSection />);
		expect(queryByText('Add integrations')).toBeNull();
		await user.click(getByRole('button', { name: /Add integration/ }));
		expect(getByPlaceholderText('Search integrations...')).toBeTruthy();
	});

	it('opens the Add MCP Server modal from the catalog Add custom button', async () => {
		const user = userEvent.setup();
		const { getByRole, getByPlaceholderText } = render(<IntegrationsSection />);
		await user.click(getByRole('button', { name: /Add integration/ }));
		await user.click(getByRole('button', { name: /Add custom/ }));
		expect(getByPlaceholderText('https://mcp.example.com/mcp')).toBeTruthy();
	});
});

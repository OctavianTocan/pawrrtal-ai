import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GeneralSection } from './GeneralSection';

const { mockCurrentUser, mockPersonalization } = vi.hoisted(() => ({
	mockCurrentUser: {
		data: {
			id: '1',
			email: 'user@example.com',
			is_active: true,
			is_superuser: false,
			is_verified: false,
		},
		isLoading: false,
		isError: false,
	},
	mockPersonalization: {
		data: { name: 'Test User', role: 'Design' },
		isLoading: false,
		isError: false,
	},
}));

vi.mock('@/hooks/use-current-user', () => ({
	useCurrentUser: () => mockCurrentUser,
}));

vi.mock('@/lib/personalization/use-personalization', () => ({
	useGetPersonalization: () => mockPersonalization,
}));

function createWrapper(): React.ComponentType<{ children: React.ReactNode }> {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe('GeneralSection', () => {
	it('renders the General page heading + every section heading', () => {
		const { getByRole, getByText } = render(<GeneralSection />, { wrapper: createWrapper() });
		expect(getByRole('heading', { name: 'General' })).toBeTruthy();
		expect(getByText('Profile')).toBeTruthy();
		expect(getByText('Notifications')).toBeTruthy();
	});

	it('renders dynamic profile data from hooks', () => {
		const { getByDisplayValue } = render(<GeneralSection />, { wrapper: createWrapper() });
		expect(getByDisplayValue('Test User')).toBeTruthy();
		expect(getByDisplayValue('Test')).toBeTruthy();
		expect(getByDisplayValue('Design')).toBeTruthy();
	});

	it('falls back to email when personalization has no name', () => {
		const prevData = mockPersonalization.data;
		mockPersonalization.data = {} as never;
		const { getByDisplayValue } = render(<GeneralSection />, { wrapper: createWrapper() });
		expect(getByDisplayValue('user@example.com')).toBeTruthy();
		mockPersonalization.data = prevData;
	});

	// The "appearance segmented control" assertion that previously lived
	// here was removed alongside the Preferences card — that affordance
	// now lives in `AppearanceSection`. The Appearance section's own
	// tests cover the System / Light / Dark toggle.
});
